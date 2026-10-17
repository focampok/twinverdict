"""Telemetría de una búsqueda real: vLLM, GPU y bucle, muestreados cada 2 s a un JSON.

Un hilo aparte muestrea mientras el bucle corre. Si /metrics o rocm-smi fallan, el evento
lleva null en esa fuente y el job sigue. La api-key de vLLM solo viaja en el header: no
se escribe en el JSON ni en los logs, que solo anotan el tipo de error.

`python -m worker.telemetry --fake` escribe una grabación de prueba marcada fake=true.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from api.live import ROOT, live_path
from config import Settings

LOG = logging.getLogger(__name__)
INTERVAL_S = 2.0
GPU_TIMEOUT_S = 5.0
HTTP_TIMEOUT_S = 3.0
GPU_SMI = (str(ROOT / "infra" / "gpu" / "gpu.sh"), "smi")
GENERATED = "vllm:generation_tokens_total"
RUNNING = "vllm:num_requests_running"

Source = Callable[[], dict[str, Any] | None]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_prometheus(text: str) -> dict[str, float]:
    """Suma de cada métrica sobre sus etiquetas. Ignora comentarios y líneas rotas."""
    totals: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "{" in line:
            name = line[: line.index("{")]
            rest = line[line.rindex("}") + 1 :].split()
        else:
            name, *rest = line.split()
        try:
            value = float(rest[0])
        except (IndexError, ValueError):
            continue
        totals[name] = totals.get(name, 0.0) + value
    return totals


def _server_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    return root[: -len("/v1")] if root.endswith("/v1") else root


def vllm_source(client: httpx.Client, base_url: str, api_key: str) -> Source:
    root = _server_root(base_url)
    headers = {"Authorization": f"Bearer {api_key}"}

    def sample() -> dict[str, Any]:
        response = client.get(f"{root}/metrics", headers=headers, timeout=HTTP_TIMEOUT_S)
        response.raise_for_status()
        metrics = parse_prometheus(response.text)
        model = None
        try:
            models = client.get(f"{root}/v1/models", headers=headers, timeout=HTTP_TIMEOUT_S)
            models.raise_for_status()
            data = models.json().get("data") or []
            model = str(data[0]["id"]) if data else None
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            LOG.warning("telemetry: /v1/models failed (%s)", type(exc).__name__)
        return {
            "model": model,
            "tokens_total": metrics.get(GENERATED),
            "requests_running": metrics.get(RUNNING),
        }

    return sample


def _first(card: dict[str, Any], *needles: str) -> str | None:
    for needle in needles:
        for key, value in card.items():
            if needle.lower() in key.lower():
                return str(value)
    return None


def _float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_rocm_smi(stdout: str) -> dict[str, Any]:
    """JSON de rocm-smi: uso %, VRAM %, potencia W y nombre de la primera tarjeta."""
    payload = json.loads(stdout[stdout.index("{") :])
    cards = sorted(key for key in payload if key.lower().startswith("card"))
    if not cards:
        raise ValueError("rocm-smi returned no card")
    card = payload[cards[0]]
    return {
        "name": _first(card, "Card Series", "Device Name", "Card model", "Card SKU"),
        "use_pct": _float(_first(card, "GPU use (%)")),
        "vram_pct": _float(_first(card, "VRAM%", "GPU memory use (%)")),
        "power_w": _float(_first(card, "Package Power (W)", "Power (W)")),
    }


def gpu_source(command: tuple[str, ...] = GPU_SMI) -> Source:
    def sample() -> dict[str, Any]:
        completed = subprocess.run(
            list(command), capture_output=True, text=True, timeout=GPU_TIMEOUT_S, check=True
        )
        return parse_rocm_smi(completed.stdout)

    return sample


class LiveRecorder:
    """Acumula eventos y reescribe el JSON entero en cada muestra (escritura atómica)."""

    def __init__(
        self,
        job_id: str,
        path: Path,
        *,
        vllm: Source,
        gpu: Source,
        interval_s: float = INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.path = path
        self.interval_s = interval_s
        self._vllm = vllm
        self._gpu = gpu
        self._clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._search: dict[str, Any] | None = None
        self._started = clock()
        self._last_tokens: tuple[float, float] | None = None
        self.payload: dict[str, Any] = {
            "job_id": job_id,
            "fake": False,
            "status": "running",
            "started_at": _now(),
            "finished_at": None,
            "interval_s": interval_s,
            "model": None,
            "gpu_name": None,
            "events": [],
        }

    def update(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self._search = dict(snapshot)

    def _read(self, name: str, source: Source) -> dict[str, Any] | None:
        try:
            return source()
        except Exception as exc:  # una fuente caída no tumba el job
            LOG.warning("telemetry: %s failed (%s)", name, type(exc).__name__)
            return None

    def sample(self) -> dict[str, Any]:
        moment = self._clock()
        vllm = self._read("vllm", self._vllm)
        gpu = self._read("gpu", self._gpu)
        if vllm is not None:
            vllm["tokens_per_s"] = self._tokens_per_s(moment, vllm.get("tokens_total"))
            self.payload["model"] = vllm.get("model") or self.payload["model"]
        if gpu is not None:
            self.payload["gpu_name"] = gpu.get("name") or self.payload["gpu_name"]
        with self._lock:
            search = None if self._search is None else dict(self._search)
        event = {
            "t": round(moment - self._started, 3),
            "ts": _now(),
            "vllm": vllm,
            "gpu": gpu,
            "search": search,
        }
        self.payload["events"].append(event)
        self.write()
        return event

    def _tokens_per_s(self, moment: float, total: object) -> float | None:
        if not isinstance(total, int | float):
            return None
        previous = self._last_tokens
        self._last_tokens = (moment, float(total))
        if previous is None or moment <= previous[0]:
            return None
        return max(0.0, (float(total) - previous[1]) / (moment - previous[0]))

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_suffix(".tmp")
        partial.write_text(json.dumps(self.payload, separators=(",", ":")) + "\n", "utf-8")
        partial.replace(self.path)

    def _loop(self) -> None:
        while True:
            self.sample()
            if self._stop.wait(self.interval_s):
                return

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="telemetry", daemon=True)
        self._thread.start()

    def stop(self, status: str) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=GPU_TIMEOUT_S + 2 * HTTP_TIMEOUT_S + 1)
        self.payload["status"] = status
        self.payload["finished_at"] = _now()
        self.sample()


def recorder_from_settings(job_id: str, settings: Settings | None = None) -> LiveRecorder:
    cfg = settings or Settings()
    client = httpx.Client()
    return LiveRecorder(
        job_id,
        live_path(job_id),
        vllm=vllm_source(client, cfg.LLM_BASE_URL, cfg.LLM_API_KEY),
        gpu=gpu_source(),
    )


def fake_recording(job_id: str, seed: int = 0, rounds: int = 8) -> dict[str, Any]:
    """Grabación de prueba con forma plausible. fake=true: la UI no la llama real."""
    rng = np.random.Generator(np.random.PCG64(seed))
    started = datetime(2026, 10, 16, 15, 0, tzinfo=UTC)
    events: list[dict[str, Any]] = []
    t = 0.0
    sims = 180
    tokens = 0.0
    counts = {"valid": 0, "invalid": 0, "duplicates": 0}
    best = 0.77
    for round_index in range(1, rounds + 1):
        for phase, samples in (("proposing", 12), ("simulating", 18)):
            if phase == "simulating":
                counts["valid"] += int(rng.integers(36, 47))
                counts["invalid"] += int(rng.integers(0, 6))
                counts["duplicates"] += int(rng.integers(0, 5))
            for _ in range(samples):
                generating = phase == "proposing"
                rate = float(rng.normal(2400, 250)) if generating else float(rng.normal(30, 10))
                tokens += max(0.0, rate) * INTERVAL_S
                if not generating:
                    sims += int(rng.integers(300, 500))
                    best = max(best, best + float(rng.normal(0.004, 0.006)))
                events.append(
                    {
                        "t": round(t, 3),
                        "ts": (started + timedelta(seconds=t)).isoformat(),
                        "vllm": {
                            "model": "Qwen/Qwen3-8B",
                            "tokens_total": tokens,
                            "tokens_per_s": max(0.0, rate),
                            "requests_running": float(rng.integers(20, 49)) if generating else 0.0,
                        },
                        "gpu": {
                            "name": "AMD Instinct MI300X (fake)",
                            "use_pct": float(
                                np.clip(rng.normal(92 if generating else 4, 4), 0, 100)
                            ),
                            "vram_pct": float(np.clip(rng.normal(91, 0.5), 0, 100)),
                            "power_w": float(rng.normal(650 if generating else 160, 30)),
                        },
                        "search": {
                            "phase": phase,
                            "round": round_index,
                            "rounds_total": rounds,
                            "proposals": dict(counts),
                            "simulations": sims,
                            "best_objective": best,
                        },
                    }
                )
                t += INTERVAL_S
    return {
        "job_id": job_id,
        "fake": True,
        "status": "done",
        "started_at": started.isoformat(),
        "finished_at": (started + timedelta(seconds=t)).isoformat(),
        "interval_s": INTERVAL_S,
        "model": "Qwen/Qwen3-8B",
        "gpu_name": "AMD Instinct MI300X (fake)",
        "events": events,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Telemetría de búsqueda")
    parser.add_argument("--fake", action="store_true", help="escribe una grabación de prueba")
    parser.add_argument("--job-id", default=None, help="por defecto REPLAY_JOB_ID")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.fake:
        parser.error("solo --fake: la grabación real la escribe el worker durante el job")
    job_id = args.job_id or Settings().REPLAY_JOB_ID
    path = live_path(job_id, fake=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fake_recording(job_id, args.seed)) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
