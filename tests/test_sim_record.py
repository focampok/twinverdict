import inspect
import json
import pickle
from pathlib import Path

import pytest

from policy.schema import MACHINES, fixed_rule_policy
from sim.config import PlantConfig
from sim.kpis import kpis_from_result
from sim.model import run_simulation
from sim.record import OFFICIAL_REPLAY, proposed_from_replay, record_seed
from sim.runner import _simulate_job, simulate

SHORT = PlantConfig(horizon_min=24 * 60)
KINDS = {"processing", "setup", "pm", "down", "idle"}
DATA = Path("netlify-visual/data")
HOLDOUT = range(1_000_001, 1_000_301)


def _lanes(intervals: list[dict], horizon: float) -> None:
    for machine in MACHINES:
        rows = [row for row in intervals if row["m"] == machine]
        assert rows, machine
        cursor = 0.0
        for row in rows:
            assert row["kind"] in KINDS
            assert row["start"] == pytest.approx(cursor, abs=1e-4)
            assert row["end"] > row["start"]
            cursor = float(row["end"])
        assert cursor == pytest.approx(horizon, abs=1e-4)


def _down_minutes(intervals: list[dict]) -> float:
    return sum(
        float(row["end"]) - float(row["start"]) for row in intervals if row["kind"] == "down"
    )


def _without_wall(metrics: dict[str, float]) -> dict[str, float]:
    return {key: value for key, value in metrics.items() if key != "sim_wall_s"}


def test_recording_does_not_change_kpis() -> None:
    policy = fixed_rule_policy()
    plain = run_simulation(policy, seed=11, config=SHORT)
    recorded: list[dict[str, float | str]] = []
    traced = run_simulation(policy, seed=11, config=SHORT, record=recorded)
    assert traced == plain
    assert _down_minutes(recorded) == pytest.approx(plain.unplanned_min, abs=1e-4)
    assert kpis_from_result(traced, 0.0) == kpis_from_result(plain, 0.0)


def test_intervals_cover_the_horizon_without_overlap() -> None:
    recorded: list[dict[str, float | str]] = []
    result = run_simulation(fixed_rule_policy(), seed=11, config=SHORT, record=recorded)
    _lanes(recorded, SHORT.horizon_min)
    assert result.orders_completed > 0
    assert {row["kind"] for row in recorded} <= KINDS
    assert "processing" in {row["kind"] for row in recorded}
    assert "idle" in {row["kind"] for row in recorded}


def test_record_none_does_nothing() -> None:
    policy = fixed_rule_policy()
    plain = run_simulation(policy, seed=11, config=SHORT)
    assert run_simulation(policy, seed=11, config=SHORT, record=None) == plain
    assert "record" not in inspect.signature(simulate).parameters


def test_simulate_stays_picklable() -> None:
    policy = fixed_rule_policy()
    job = (policy, 4, SHORT, "base")
    assert pickle.loads(pickle.dumps(simulate)) is not None
    assert pickle.loads(pickle.dumps(_simulate_job)) is not None
    restored = pickle.loads(pickle.dumps(job))
    left = _without_wall(simulate(policy, 4, SHORT))
    right = _without_wall(_simulate_job(restored))
    assert left == right


def test_search_loop_does_not_call_the_recorder() -> None:
    for relative in ("search/loop.py", "sim/runner.py", "worker/main.py"):
        text = Path(relative).read_text(encoding="utf-8")
        assert "sim.record" not in text
        assert "record_seed" not in text


def test_proposed_policy_is_read_from_the_replay() -> None:
    policy = proposed_from_replay(OFFICIAL_REPLAY)
    raw = json.loads(OFFICIAL_REPLAY.read_text(encoding="utf-8"))["best_policy"]
    assert policy.model_dump(by_alias=True) == raw


def test_record_seed_keeps_both_policies() -> None:
    proposed = proposed_from_replay(OFFICIAL_REPLAY)
    payload = record_seed(1_000_001, proposed, SHORT)
    assert payload["seed"] == 1_000_001
    assert set(payload["policies"]) == {"baseline", "proposed"}
    for side in payload["policies"].values():
        _lanes(side["intervals"], SHORT.horizon_min)
        assert _down_minutes(side["intervals"]) == pytest.approx(
            side["kpis"]["unplanned_min"], abs=1e-3
        )


def test_versioned_intervals_are_divergent_holdout_seeds() -> None:
    paths = sorted(DATA.glob("intervals_*.json"))
    assert len(paths) == 3
    horizon = PlantConfig().horizon_min
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        seed = int(payload["seed"])
        assert seed in HOLDOUT
        assert path.name == f"intervals_{seed}.json"
        baseline = payload["policies"]["baseline"]
        proposed = payload["policies"]["proposed"]
        assert baseline["kpis"]["unplanned_min"] > proposed["kpis"]["unplanned_min"]
        for side in (baseline, proposed):
            _lanes(side["intervals"], horizon)
            assert _down_minutes(side["intervals"]) == pytest.approx(
                side["kpis"]["unplanned_min"], abs=1e-3
            )
