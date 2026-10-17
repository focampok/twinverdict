import time
from dataclasses import replace

import pytest
from pydantic import ValidationError

from policy.schema import fixed_rule_policy
from sim.config import PlantConfig
from sim.model import run_simulation
from sim.runner import simulate, simulate_many

SHORT = PlantConfig(horizon_min=24 * 60)


def _without_wall(metrics: dict[str, float]) -> dict[str, float]:
    return {key: value for key, value in metrics.items() if key != "sim_wall_s"}


def test_short_run_finishes_processes_orders_and_bounds_wear() -> None:
    result = run_simulation(fixed_rule_policy(), seed=7, config=SHORT)
    assert result.orders_created > 0
    assert result.orders_completed > 0
    assert result.orders_created == result.orders_completed + result.orders_wip
    assert 0.0 <= result.wear_min <= result.wear_max <= 1.0


def test_same_seed_same_arrivals_across_policies() -> None:
    other = replace_dispatch_spt()
    base = run_simulation(fixed_rule_policy(), seed=3, config=SHORT)
    alt = run_simulation(other, seed=3, config=SHORT)
    assert base.arrival_times == alt.arrival_times
    assert base.process_times == alt.process_times


def replace_dispatch_spt():
    from policy.schema import parse_policy

    raw = fixed_rule_policy().model_dump(by_alias=True)
    raw["dispatch"]["rule"] = "SPT"
    return parse_policy(raw)


def test_same_seed_same_metrics() -> None:
    policy = fixed_rule_policy()
    first = _without_wall(simulate(policy, seed=11, config=SHORT))
    second = _without_wall(simulate(policy, seed=11, config=SHORT))
    assert first == second


def test_different_seeds_differ() -> None:
    policy = fixed_rule_policy()
    first = _without_wall(simulate(policy, seed=1, config=SHORT))
    second = _without_wall(simulate(policy, seed=2, config=SHORT))
    assert first != second


def test_order_conservation() -> None:
    metrics = simulate(fixed_rule_policy(), seed=5, config=SHORT)
    assert metrics["orders_created"] == metrics["orders_completed"] + metrics["orders_wip"]


def test_simulate_many_matches_serial() -> None:
    policy = fixed_rule_policy()
    seeds = [4, 5]
    serial = [_without_wall(simulate(policy, seed, config=SHORT)) for seed in seeds]
    many = simulate_many(policy, seeds, workers=2, config=SHORT)
    parallel = [_without_wall(row) for row in many]
    assert parallel == serial


def test_spawn_pool_mini_round_not_much_slower_than_serial() -> None:
    """Pool spawn reutilizado: una mini-ronda no debe ir mucho peor que en serie."""
    policy = fixed_rule_policy()
    seeds = list(range(12))
    rounds = 5
    # Calienta el pool spawn compartido (el coste de arranque no cuenta en la ronda).
    simulate_many(policy, seeds, workers=2, config=SHORT)
    started = time.perf_counter()
    for _ in range(rounds):
        simulate_many(policy, seeds, workers=1, config=SHORT)
    serial_s = time.perf_counter() - started
    started = time.perf_counter()
    for _ in range(rounds):
        simulate_many(policy, seeds, workers=2, config=SHORT)
    spawn_s = time.perf_counter() - started
    # Margen holgado para CI cargada; en local spawn suele ser claramente más rápido.
    assert spawn_s <= serial_s * 1.25, f"spawn {spawn_s:.3f}s vs serial {serial_s:.3f}s"


def test_stress_has_more_failures_on_average() -> None:
    policy = fixed_rule_policy()
    seeds = list(range(10))
    base = [simulate(policy, seed, scenario="base")["failures_total"] for seed in seeds]
    stress = [simulate(policy, seed, scenario="stress")["failures_total"] for seed in seeds]
    assert sum(stress) / len(stress) > sum(base) / len(base)


def test_invalid_policy_raises_before_simulating() -> None:
    with pytest.raises(ValidationError):
        simulate({"dispatch": {"rule": "NOPE"}}, seed=1)


def test_stress_scales_failure_and_demand() -> None:
    from sim.runner import scenario_config

    cfg = scenario_config(PlantConfig(), "stress")
    assert cfg.failure_rate_scale == pytest.approx(1.3)
    assert cfg.demand_scale == pytest.approx(1.5)
    untouched = scenario_config(replace(PlantConfig(), failure_rate_scale=2.0), "base")
    assert untouched.failure_rate_scale == 2.0
