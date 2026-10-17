"""Grabaciones de telemetría de una búsqueda: lectura y reproducción acelerada.

Una grabación es data/replay/live_<job_id>.json. La de prueba (`--fake`) se llama
live_<job_id>.fake.json y siempre se trata como fake, diga lo que diga su contenido.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR = ROOT / "data" / "replay"
SPEEDS = (1, 10, 30)
DEFAULT_SPEED = 30
TICK_S = 1.0
SERIES_POINTS = 150


def live_path(job_id: str, *, fake: bool = False, live_dir: Path | None = None) -> Path:
    base = LIVE_DIR if live_dir is None else live_dir
    return base / f"live_{job_id}{'.fake' if fake else ''}.json"


def load_recording(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["fake"] = bool(payload.get("fake")) or path.name.endswith(".fake.json")
    events = payload.get("events") or []
    # sorted es estable: dos eventos con el mismo t quedan en el orden grabado.
    payload["events"] = sorted(events, key=lambda event: float(event["t"]))
    return payload


def replay_recording(job_id: str) -> dict[str, Any] | None:
    """La grabación real del job; si no existe, la de prueba."""
    for fake in (False, True):
        path = live_path(job_id, fake=fake)
        if path.is_file():
            return load_recording(path)
    return None


def current_recording() -> dict[str, Any] | None:
    """MODE=live: la grabación más reciente que escribe el worker. Nunca una fake."""
    if not LIVE_DIR.is_dir():
        return None
    paths = [path for path in LIVE_DIR.glob("live_*.json") if not path.name.endswith(".fake.json")]
    if not paths:
        return None
    path = max(paths, key=lambda item: item.stat().st_mtime)
    try:
        return load_recording(path)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        # Lectura a medias o JSON aún vacío: el poll de /live reintenta.
        return None


def parse_speed(raw: object) -> int:
    try:
        speed = int(str(raw))
    except ValueError:
        return DEFAULT_SPEED
    return speed if speed in SPEEDS else DEFAULT_SPEED


def parse_position(raw: object) -> float:
    try:
        position = float(str(raw))
    except ValueError:
        return 0.0
    return position if position >= 0 else 0.0


def next_position(position: float, speed: int) -> float:
    return position + speed * TICK_S


def duration(recording: dict[str, Any]) -> float:
    events = recording["events"]
    return float(events[-1]["t"]) if events else 0.0


def frame(recording: dict[str, Any], position: float) -> dict[str, Any]:
    """Lo que se ve en `position` segundos de grabación: el último evento y la serie."""
    shown = [event for event in recording["events"] if float(event["t"]) <= position]
    total = duration(recording)
    window = shown[-SERIES_POINTS:]

    def _gpu(key: str) -> list[float | None]:
        return [(event.get("gpu") or {}).get(key) for event in window]

    return {
        "event": shown[-1] if shown else None,
        "shown": len(shown),
        "position": min(position, total),
        "duration": total,
        "finished": position >= total,
        "series": {
            "t": [float(event["t"]) for event in window],
            "use_pct": _gpu("use_pct"),
            "vram_pct": _gpu("vram_pct"),
            "power_w": _gpu("power_w"),
        },
    }


def model_label(model: str | None) -> str:
    if not model:
        return "—"
    return f"{model.rsplit('/', 1)[-1]} via vLLM"


def clock(timestamp: str | None) -> str:
    if not timestamp:
        return "—"
    return datetime.fromisoformat(timestamp).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
