import json
import logging
import re
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import worker.telemetry as telemetry
from api import live
from api.main import create_app
from llm.client import LLMClient
from llm.mock_server import app as mock_app
from search.config import SearchConfig
from search.loop import run_search
from worker.telemetry import (
    LiveRecorder,
    fake_recording,
    gpu_source,
    parse_prometheus,
    parse_rocm_smi,
    vllm_source,
)

JOB = "285d1787-5d7c-464a-9897-4c585663f088"
SECRET = "sk-vllm-SECRET-4f1e"
METRICS = """# HELP vllm:generation_tokens_total Number of generation tokens processed.
# TYPE vllm:generation_tokens_total counter
vllm:generation_tokens_total{model_name="Qwen/Qwen3-8B"} 1000.0
vllm:generation_tokens_created{model_name="Qwen/Qwen3-8B"} 1.76e+09
vllm:num_requests_running{model_name="Qwen/Qwen3-8B"} 12.0
"""
ROCM_SMI = json.dumps(
    {
        "card0": {
            "GPU use (%)": "87",
            "GPU Memory Allocated (VRAM%)": "91",
            "Current Socket Graphics Package Power (W)": "612.0",
            "Card Series": "AMD Instinct MI300X",
        },
        "system": {"Driver version": "6.10.5"},
    }
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _vllm_transport(tokens: list[float]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        if request.url.path == "/metrics":
            body = METRICS.replace("1000.0", str(tokens[0]))
            return httpx.Response(200, text=body)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "Qwen/Qwen3-8B"}]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _broken(*_: object) -> dict:
    raise subprocess.CalledProcessError(255, ["gpu.sh", "smi"], stderr=f"key {SECRET}")


def test_parsers_read_vllm_metrics_and_rocm_smi() -> None:
    metrics = parse_prometheus(METRICS)
    assert metrics["vllm:generation_tokens_total"] == 1000.0
    assert metrics["vllm:num_requests_running"] == 12.0
    gpu = parse_rocm_smi("WARNING: noise before the json\n" + ROCM_SMI)
    assert gpu == {
        "name": "AMD Instinct MI300X",
        "use_pct": 87.0,
        "vram_pct": 91.0,
        "power_w": 612.0,
    }


def test_sampler_tolerates_failing_rocm_smi_and_metrics(tmp_path: Path) -> None:
    clock = Clock()
    tokens = [1000.0]
    state = {"metrics_up": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if not state["metrics_up"]:
            raise httpx.ConnectError(f"refused, Bearer {SECRET}")
        return _vllm_transport(tokens).handle_request(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    recorder = LiveRecorder(
        "job",
        tmp_path / "live_job.json",
        vllm=vllm_source(client, "http://127.0.0.1:8000/v1", SECRET),
        gpu=_broken,
        clock=clock,
    )
    recorder.update({"round": 1, "simulations": 180})
    first = recorder.sample()
    clock.now += 2.0
    tokens[0] = 5000.0
    second = recorder.sample()
    state["metrics_up"] = False
    clock.now += 2.0
    third = recorder.sample()
    assert first["gpu"] is None and second["gpu"] is None
    assert first["vllm"]["tokens_per_s"] is None
    assert second["vllm"]["tokens_per_s"] == pytest.approx(2000.0)
    assert second["vllm"]["requests_running"] == 12.0
    assert third["vllm"] is None
    assert third["search"] == {"round": 1, "simulations": 180}
    saved = json.loads((tmp_path / "live_job.json").read_text())
    assert [event["t"] for event in saved["events"]] == [0.0, 2.0, 4.0]
    assert saved["model"] == "Qwen/Qwen3-8B"
    assert saved["fake"] is False


def test_gpu_source_timeout_is_a_null_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telemetry, "GPU_TIMEOUT_S", 0.2)
    recorder = LiveRecorder(
        "job",
        tmp_path / "live_job.json",
        vllm=lambda: None,
        gpu=gpu_source(("sleep", "30")),
    )
    event = recorder.sample()
    assert event["gpu"] is None


def test_thread_records_until_stopped(tmp_path: Path) -> None:
    recorder = LiveRecorder(
        "job", tmp_path / "live_job.json", vllm=_broken, gpu=_broken, interval_s=0.05
    )
    recorder.start()
    recorder.update({"round": 2})
    time.sleep(0.3)
    recorder.stop("done")
    saved = json.loads((tmp_path / "live_job.json").read_text())
    assert saved["status"] == "done"
    assert saved["finished_at"]
    assert len(saved["events"]) >= 3
    times = [event["t"] for event in saved["events"]]
    assert times == sorted(times)


def test_no_secret_in_json_or_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # alembic.fileConfig, en los tests de base, deshabilita los loggers ya creados.
    monkeypatch.setattr(telemetry.LOG, "disabled", False)
    caplog.set_level(logging.DEBUG)
    clock = Clock()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            raise httpx.ReadTimeout(f"timeout with {request.headers['Authorization']}")
        return _vllm_transport([10.0]).handle_request(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    path = tmp_path / "live_job.json"
    recorder = LiveRecorder(
        "job",
        path,
        vllm=vllm_source(client, "http://127.0.0.1:8000/v1", SECRET),
        gpu=_broken,
        clock=clock,
    )
    recorder.sample()
    recorder.stop("failed")
    assert SECRET not in path.read_text()
    assert SECRET not in caplog.text
    assert "ReadTimeout" in caplog.text


async def test_search_reports_progress() -> None:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://test")
    client = LLMClient(
        base_url="http://test/v1", model="mock", api_key="mock", concurrency=4, http_client=http
    )
    config = SearchConfig.from_profile("smoke")
    snapshots: list[dict] = []
    try:
        result = await run_search(
            config, client, "base", 1, workers=1, holdout_seeds=0, progress=snapshots.append
        )
    finally:
        await client.aclose()
        await http.aclose()
    assert snapshots[0]["phase"] == "fixed"
    assert snapshots[-1]["phase"] == "done"
    assert snapshots[-1]["simulations"] == result.simulations_total
    assert snapshots[-1]["best_objective"] == result.best_objective
    sims = [item["simulations"] for item in snapshots]
    assert sims == sorted(sims)
    valid = sum(len(item.valid) for item in result.rounds)
    assert snapshots[-1]["proposals"]["valid"] == valid


async def test_mock_search_with_sampler_and_process_pool_finishes(tmp_path: Path) -> None:
    """El hilo de telemetría no debe colgar el ProcessPool (spawn, no fork)."""
    assert telemetry.GPU_TIMEOUT_S == 5.0
    path = tmp_path / "live_job.json"
    recorder = LiveRecorder(
        "job",
        path,
        vllm=lambda: {"model": "mock", "tokens_total": 1.0, "requests_running": 0.0},
        gpu=gpu_source(("sleep", "0.05")),
        interval_s=0.05,
    )
    recorder.start()
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://test")
    client = LLMClient(
        base_url="http://test/v1", model="mock", api_key="mock", concurrency=4, http_client=http
    )
    config = SearchConfig.from_profile("smoke")
    started = time.perf_counter()
    try:
        result = await run_search(
            config, client, "base", 1, workers=2, holdout_seeds=0, progress=recorder.update
        )
    finally:
        await client.aclose()
        await http.aclose()
        recorder.stop("done")
    elapsed = time.perf_counter() - started
    assert result.simulations_total > 0
    assert elapsed < 60.0, f"job mock con sampler se colgó o fue demasiado lento: {elapsed:.1f}s"
    saved = json.loads(path.read_text())
    assert saved["status"] == "done"
    assert saved["finished_at"]
    assert len(saved["events"]) >= 2
    assert any((event.get("search") or {}).get("phase") == "done" for event in saved["events"])


def _recording(fake: bool) -> dict:
    events = [
        {"t": 4.0, "ts": "2026-10-16T15:00:04+00:00", "search": {"round": 3}, "gpu": None},
        {"t": 0.0, "ts": "2026-10-16T15:00:00+00:00", "search": {"round": 1}, "gpu": None},
        {"t": 2.0, "ts": "2026-10-16T15:00:02+00:00", "search": {"round": 2}, "gpu": None},
        {"t": 2.0, "ts": "2026-10-16T15:00:02+00:00", "search": {"round": 22}, "gpu": None},
        {"t": 90.0, "ts": "2026-10-16T15:01:30+00:00", "search": {"round": 8}, "gpu": None},
    ]
    return {
        "job_id": JOB,
        "fake": fake,
        "status": "done",
        "started_at": "2026-10-16T15:00:00+00:00",
        "model": "Qwen/Qwen3-8B",
        "gpu_name": "AMD Instinct MI300X",
        "events": events,
    }


def test_replay_respects_order_and_speed(tmp_path: Path) -> None:
    path = tmp_path / "live_x.json"
    path.write_text(json.dumps(_recording(False)))
    recording = live.load_recording(path)
    assert [event["search"]["round"] for event in recording["events"]] == [1, 2, 22, 3, 8]
    assert live.frame(recording, 1.0)["event"]["search"]["round"] == 1
    assert live.frame(recording, 2.0)["event"]["search"]["round"] == 22
    assert live.frame(recording, 30.0)["shown"] == 4
    assert live.frame(recording, 30.0)["finished"] is False
    assert live.frame(recording, 90.0)["finished"] is True
    assert live.next_position(0.0, 30) == 30.0
    assert live.next_position(30.0, 10) == 40.0
    assert live.next_position(40.0, 1) == 41.0
    assert live.parse_speed("7") == live.DEFAULT_SPEED == 30


@pytest.fixture
def replay_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(live, "LIVE_DIR", tmp_path)
    monkeypatch.setenv("MODE", "replay")
    monkeypatch.setenv("REPLAY_JOB_ID", JOB)
    return tmp_path


def test_frame_endpoint_advances_by_speed(replay_dir: Path) -> None:
    live.live_path(JOB).write_text(json.dumps(_recording(False)))
    with TestClient(create_app()) as client:
        first = client.get("/live/frame", params={"pos": "0", "speed": "30"})
        slow = client.get("/live/frame", params={"pos": "30", "speed": "1"})
        end = client.get("/live/frame", params={"pos": "120", "speed": "30"})
    assert 'hx-get="/live/frame?pos=30.0&amp;speed=30"' in first.text
    assert 'hx-get="/live/frame?pos=31.0&amp;speed=1"' in slow.text
    assert "hx-trigger" not in end.text
    assert "Restart" in end.text


def test_real_recording_shows_the_badge(replay_dir: Path) -> None:
    live.live_path(JOB).write_text(json.dumps(_recording(False)))
    with TestClient(create_app()) as client:
        page = client.get("/live")
        card = client.get("/")
    assert "Recorded run · real vLLM on MI300X" in page.text
    assert "Qwen3-8B via vLLM" in page.text
    assert "AMD Instinct MI300X · ROCm" in page.text
    assert "2026-10-16 15:00:00 UTC" in page.text
    assert 'href="/live"' in card.text


@pytest.mark.parametrize("as_file", [False, True])
def test_fake_recording_never_says_real(replay_dir: Path, as_file: bool) -> None:
    payload = fake_recording(JOB) if as_file else _recording(True)
    if as_file:
        live.live_path(JOB, fake=True).write_text(json.dumps({**payload, "fake": False}))
    else:
        live.live_path(JOB).write_text(json.dumps(payload))
    with TestClient(create_app()) as client:
        page = client.get("/live")
        frame = client.get("/live/frame", params={"pos": "60", "speed": "10"})
    assert page.status_code == frame.status_code == 200
    assert "fake data" in page.text
    for text in (page.text, frame.text):
        assert not re.search(r"\breal\b", text, re.IGNORECASE)


def test_missing_recording_says_so(replay_dir: Path) -> None:
    with TestClient(create_app()) as client:
        page = client.get("/live")
    assert page.status_code == 200
    assert "No recording for this run yet." in page.text
    assert not re.search(r"\breal\b", page.text, re.IGNORECASE)
    assert "hx-trigger" not in page.text


def test_live_mode_polls_until_recording_appears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "LIVE_DIR", tmp_path)
    monkeypatch.setenv("MODE", "live")
    with TestClient(create_app()) as client:
        page = client.get("/live")
        frame = client.get("/live/frame", params={"pos": "0", "speed": "30"})
    assert page.status_code == frame.status_code == 200
    assert "No recording for this run yet." in page.text
    for text in (page.text, frame.text):
        assert 'hx-get="/live/frame?pos=0.0&amp;speed=30"' in text
        assert 'hx-trigger="load delay:1s"' in text


def test_fake_generator_is_marked_and_ordered() -> None:
    payload = fake_recording(JOB)
    assert payload["fake"] is True
    times = [event["t"] for event in payload["events"]]
    assert times == sorted(times)
    assert payload["events"][-1]["search"]["round"] == 8
