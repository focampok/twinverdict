"""Build the 3-minute demo video from the two screen recordings plus ElevenLabs voice-over.

Usage (from the repo root):

    uv run python video/build.py detect   # 1 fps frames + clip1 section boundaries → segments.json
    uv run python video/build.py build    # voice-over, cut, concat, loudnorm → twinverdict_demo.mp4

Inputs live outside git (docs/clips/), outputs go to video/out/ (also ignored). The only
versioned artifacts are this script and video/segments.json.

Rules implemented here:
- Each segment lasts exactly voice duration + PAD_TOTAL seconds (a short lead-in, the rest as tail),
  plus an optional per-segment ``"hold"`` (extra seconds) set in segments.json.
- Deck segments are never sped up: longer clips are cut, shorter ones freeze the last frame.
- Segments flagged ``"fit": true`` (the /live tramo) may be sped up with setpts to fit the voice.
- Segments are joined with a 0.3 s cross-fade; the voice of the incoming segment is not faded.
- Final mix is 1920x1080, 30 fps, H.264 + AAC, two-pass loudnorm to -16 LUFS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "docs" / "clips"
VIDEO_DIR = ROOT / "video"
OUT = VIDEO_DIR / "out"
VO_DIR = OUT / "vo"
FRAMES_DIR = OUT / "frames"
SEG_DIR = OUT / "segments"
SEGMENTS_JSON = VIDEO_DIR / "segments.json"
FINAL = OUT / "twinverdict_demo.mp4"

WIDTH, HEIGHT, FPS = 1920, 1080, 30
PAD_LEAD = 0.1  # silence before the voice starts
PAD_TOTAL = 0.4  # segment = voice + PAD_TOTAL (lead + tail)
XFADE = 0.3
TARGET_LUFS = -16.0

ELEVEN_MODEL = "eleven_multilingual_v2"
ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# clip1 deck sections in slide order. Roadmap is not in the recording (the deck stops at 8/9).
DECK_SECTIONS = [
    "Hook",
    "Problem",
    "Solution",
    "Results",
    "See it run",
    "Powered by AMD",
    "Who uses it",
    "Try it yourself",
]


# --------------------------------------------------------------------------- helpers


def run(cmd: list[str], *, capture: bool = False) -> str:
    """Run a command, fail loudly, optionally return stdout+stderr."""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr[-4000:])
        raise SystemExit(f"command failed ({res.returncode}): {' '.join(cmd[:4])} ...")
    return res.stdout + res.stderr if capture else ""


def probe_duration(path: Path) -> float:
    out = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture=True,
    )
    return float(out.strip().splitlines()[0])


def load_env(path: Path = ROOT / ".env") -> dict[str, str]:
    """Minimal .env reader (KEY=VALUE, '#' comments). Values are never printed."""
    env: dict[str, str] = dict(os.environ)
    if path.exists():
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def fmt_mmss(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:05.2f}"


# --------------------------------------------------------------------------- detect


def extract_frames(clip: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob(f"{clip.stem}_*.jpg"):
        old.unlink()
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(clip),
            "-vf",
            "fps=1",
            "-q:v",
            "4",
            str(dest / f"{clip.stem}_%04d.jpg"),
        ]
    )


def frame_diffs(clip: Path) -> np.ndarray:
    """Mean absolute difference between consecutive 1 fps gray frames (downscaled)."""
    res = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(clip),
            "-vf",
            "fps=1,scale=192:108,format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    frames = np.frombuffer(res.stdout, dtype=np.uint8).reshape(-1, 108, 192).astype(np.float32)
    return np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))


def scene_times(clip: Path, start: float, length: float, threshold: float) -> list[float]:
    """Timestamps where ffmpeg's scene score exceeds threshold inside [start, start+length]."""
    out = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{length:.3f}",
            "-i",
            str(clip),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture=True,
    )
    return [start + float(m) for m in re.findall(r"pts_time:([0-9.]+)", out)]


def detect_sections(clip: Path, coarse_threshold: float = 2.5) -> list[dict[str, float | str]]:
    """Find where each deck section starts/ends in clip1.

    Coarse pass: per-second frame difference (catches slow fades the scene filter misses).
    Fine pass: ffmpeg scene scores around each coarse hit; a section starts when the
    transition settles and the previous one ends when it begins.
    """
    diffs = frame_diffs(clip)
    hits = [i + 1 for i, d in enumerate(diffs) if d > coarse_threshold]
    coarse: list[int] = []
    for t in hits:  # cluster adjacent seconds into one boundary
        if not coarse or t - coarse[-1] > 2:
            coarse.append(t)
    total = probe_duration(clip)
    boundaries: list[tuple[float, float]] = []  # (transition begins, transition settles)
    for t in coarse:
        times = scene_times(clip, max(0.0, t - 1.5), 3.0, 0.01)
        if times:
            boundaries.append((round(times[0] - 0.02, 2), round(times[-1] + 0.08, 2)))
        else:
            boundaries.append((float(t), float(t)))
    if len(boundaries) != len(DECK_SECTIONS) - 1:
        names = [f"{a:.2f}" for a, _ in boundaries]
        raise SystemExit(
            f"expected {len(DECK_SECTIONS) - 1} boundaries, found {len(boundaries)}: {names}"
        )
    sections: list[dict[str, float | str]] = []
    start = 0.0
    for name, (ends, next_start) in zip(DECK_SECTIONS, boundaries + [(total, total)], strict=True):
        sections.append({"name": name, "start": round(start, 2), "end": round(ends, 2)})
        start = next_start
    return sections


def cmd_detect() -> None:
    clip1 = CLIPS / "clip1.mp4"
    extract_frames(clip1, FRAMES_DIR)
    sections = detect_sections(clip1)
    data = json.loads(SEGMENTS_JSON.read_text()) if SEGMENTS_JSON.exists() else {}
    data["clip1_sections"] = sections
    SEGMENTS_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"frames: {FRAMES_DIR} ({len(list(FRAMES_DIR.glob('clip1_*.jpg')))} at 1 fps)")
    print("clip1 sections:")
    for s in sections:
        print(f"  {s['name']:<16} {s['start']:>7.2f} → {s['end']:>7.2f}  ({fmt_mmss(s['start'])})")
    print(f"saved → {SEGMENTS_JSON}")


# --------------------------------------------------------------------------- build


@dataclass(frozen=True)
class Segment:
    id: str
    source: Path
    start: float
    end: float
    text: str
    fit: bool
    hold: float = 0.0  # optional extra seconds after the voice (default: none)


def load_segments() -> list[Segment]:
    data = json.loads(SEGMENTS_JSON.read_text())
    sections = {s["name"]: s for s in data.get("clip1_sections", [])}
    segments: list[Segment] = []
    for raw in data["segments"]:
        if "section" in raw:
            sec = sections[raw["section"]]
            start, end = float(sec["start"]), float(sec["end"])
        else:
            start, end = float(raw["start"]), float(raw["end"])
        segments.append(
            Segment(
                id=raw["id"],
                source=CLIPS / raw["source"],
                start=start,
                end=end,
                text=raw["text"].strip(),
                fit=bool(raw.get("fit", False)),
                hold=float(raw.get("hold", 0.0)),
            )
        )
    return segments


def voice_path(seg: Segment, voice_id: str) -> Path:
    digest = hashlib.sha1(f"{ELEVEN_MODEL}|{voice_id}|{seg.text}".encode()).hexdigest()[:12]
    return VO_DIR / f"{seg.id}_{digest}.mp3"


def synthesize(seg: Segment, api_key: str, voice_id: str) -> Path:
    """Fetch the MP3 for a segment from ElevenLabs unless it is already cached."""
    path = voice_path(seg, voice_id)
    if path.exists() and path.stat().st_size > 0:
        return path
    VO_DIR.mkdir(parents=True, exist_ok=True)
    resp = httpx.post(
        ELEVEN_URL.format(voice_id=voice_id),
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": seg.text, "model_id": ELEVEN_MODEL},
        timeout=120,
    )
    if resp.status_code != 200:
        raise SystemExit(f"ElevenLabs {resp.status_code} on {seg.id}: {resp.text[:300]}")
    path.write_bytes(resp.content)
    return path


def render_segment(seg: Segment, voice: Path, duration: float) -> Path:
    """Cut/pad the clip tramo to `duration` seconds and mux the voice (lead-in + tail)."""
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    out = SEG_DIR / f"{seg.id}.mkv"  # PCM audio keeps the cross-fades free of AAC priming gaps
    src_len = seg.end - seg.start
    chain = [f"fps={FPS}", f"scale={WIDTH}:{HEIGHT}:flags=bicubic", "setsar=1"]
    if seg.fit and src_len > duration:
        chain.insert(0, f"setpts=PTS*{duration / src_len:.6f}")
    chain += [
        f"tpad=stop_mode=clone:stop_duration={duration:.3f}",
        f"trim=duration={duration:.3f}",
        "setpts=PTS-STARTPTS",
        "format=yuv420p",
    ]
    audio = (
        f"[1:a]aresample=48000,adelay={int(PAD_LEAD * 1000)}:all=1,apad,"
        f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[a]"
    )
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{seg.start:.3f}",
            "-t",
            f"{src_len:.3f}",
            "-i",
            str(seg.source),
            "-i",
            str(voice),
            "-filter_complex",
            f"[0:v]{','.join(chain)}[v];{audio}",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-r",
            str(FPS),
            "-c:a",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(out),
        ]
    )
    return out


def concat_with_xfade(parts: list[Path], durations: list[float], loudnorm: str, dest: Path) -> None:
    inputs: list[str] = []
    for p in parts:
        inputs += ["-i", str(p)]
    filt: list[str] = []
    v_prev, a_prev = "[0:v]", "[0:a]"
    offset = 0.0
    for i in range(1, len(parts)):
        offset += durations[i - 1] - XFADE
        v_out = f"[v{i}]" if i < len(parts) - 1 else "[vout]"
        a_out = f"[a{i}]" if i < len(parts) - 1 else "[amix]"
        filt.append(
            f"{v_prev}[{i}:v]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}{v_out}"
        )
        filt.append(f"{a_prev}[{i}:a]acrossfade=d={XFADE}:c1=tri:c2=nofade{a_out}")
        v_prev, a_prev = v_out, a_out
    filt.append(f"[amix]{loudnorm}[aout]")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filt),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )


def measure_loudness(parts: list[Path], durations: list[float]) -> str:
    """First loudnorm pass on the cross-faded mix; returns the filter string for pass two."""
    tmp = OUT / "_mix_pass1.mkv"
    concat_with_xfade(parts, durations, "anull", tmp)
    log = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(tmp),
            "-vn",
            "-af",
            f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture=True,
    )
    tmp.unlink()
    stats = json.loads(log[log.rfind("{") :])
    return (
        f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11:linear=true"
        f":measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
        f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}"
    )


def cmd_build(skip_loudnorm_measure: bool = False) -> None:
    env = load_env()
    api_key = env.get("ELEVENLABS_API_KEY")
    voice_id = env.get("ELEVENLABS_VOICE_ID_EN_MALE")
    if not api_key or not voice_id:
        raise SystemExit("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID_EN_MALE must be set in .env")
    segments = load_segments()
    OUT.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    durations: list[float] = []
    print(f"{'seg':<4} {'source':<10} {'clip tramo':>16} {'voice':>7} {'seg':>7}  note")
    for seg in segments:
        voice = synthesize(seg, api_key, voice_id)
        vo_len = probe_duration(voice)
        duration = round(vo_len + PAD_TOTAL + seg.hold, 3)
        src_len = seg.end - seg.start
        if seg.fit and src_len > duration:
            note = f"sped up x{src_len / duration:.2f}"
        elif src_len > duration:
            note = f"cut (-{src_len - duration:.1f}s)"
        elif src_len < duration:
            note = f"freeze last frame (+{duration - src_len:.1f}s)"
        else:
            note = ""
        part = render_segment(seg, voice, duration)
        actual = probe_duration(part)
        parts.append(part)
        durations.append(actual)
        print(
            f"{seg.id:<4} {seg.source.name:<10} {seg.start:>7.2f}→{seg.end:>7.2f} "
            f"{vo_len:>7.2f} {actual:>7.2f}  {note}"
        )

    loudnorm = (
        f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11"
        if skip_loudnorm_measure
        else measure_loudness(parts, durations)
    )
    concat_with_xfade(parts, durations, loudnorm, FINAL)
    total = probe_duration(FINAL)
    print(f"\n{FINAL}")
    print(f"total: {fmt_mmss(total)} ({total:.2f} s)")
    if total > 180:
        over = total - 180
        longest = max(zip(segments, durations, strict=True), key=lambda x: x[1])
        print(
            f"OVER 3:00 by {over:.1f}s. Longest segment: {longest[0].id} ({longest[1]:.1f}s). "
            "Trim the clip tramo or the voice, not the text."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect", help="extract frames at 1 fps and locate deck sections in clip1")
    b = sub.add_parser("build", help="synthesize voice-over, cut, concat and loudnorm")
    b.add_argument("--fast", action="store_true", help="single-pass loudnorm (quicker)")
    args = parser.parse_args()
    if args.cmd == "detect":
        cmd_detect()
    else:
        cmd_build(skip_loudnorm_measure=args.fast)


if __name__ == "__main__":
    main()
