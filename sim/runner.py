"""simulate() pura: sin red, disco ni base de datos. El retorno es picklable."""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from typing import Literal

from policy.schema import Policy, parse_policy
from sim.config import PlantConfig
from sim.kpis import kpis_from_result
from sim.model import run_simulation

Scenario = Literal["base", "stress"]


def scenario_config(config: PlantConfig | None, scenario: Scenario) -> PlantConfig:
    cfg = config or PlantConfig()
    if scenario == "base":
        return cfg
    if scenario == "stress":
        return replace(
            cfg,
            failure_rate_scale=cfg.failure_rate_scale * 1.3,
            demand_scale=cfg.demand_scale * 1.5,
        )
    raise ValueError(f"escenario desconocido: {scenario}")


def simulate(
    policy: Policy | dict,
    seed: int,
    config: PlantConfig | None = None,
    scenario: Scenario = "base",
) -> dict[str, float]:
    if not isinstance(policy, Policy):
        policy = parse_policy(policy)
    cfg = scenario_config(config, scenario)
    started = time.perf_counter()
    result = run_simulation(policy, seed, cfg)
    wall_s = time.perf_counter() - started
    return kpis_from_result(result, wall_s)


def _simulate_job(job: tuple[Policy | dict, int, PlantConfig | None, Scenario]) -> dict[str, float]:
    policy, seed, config, scenario = job
    return simulate(policy, seed, config, scenario)


def simulate_many(
    policy: Policy | dict,
    seeds: list[int] | tuple[int, ...],
    workers: int,
    config: PlantConfig | None = None,
    scenario: Scenario = "base",
) -> list[dict[str, float]]:
    """Misma política en varias semillas. workers>1 usa ProcessPoolExecutor."""
    seed_list = [int(seed) for seed in seeds]
    if workers <= 1 or len(seed_list) <= 1:
        return [simulate(policy, seed, config, scenario) for seed in seed_list]
    jobs = [(policy, seed, config, scenario) for seed in seed_list]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_simulate_job, jobs))
