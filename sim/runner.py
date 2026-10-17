"""simulate() pura: sin red, disco ni base de datos. El retorno es picklable."""

from __future__ import annotations

import atexit
import multiprocessing
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from typing import Literal

from policy.schema import Policy, parse_policy
from sim.config import PlantConfig
from sim.kpis import kpis_from_result
from sim.model import run_simulation

Scenario = Literal["base", "stress"]
# spawn: el worker puede tener el hilo de telemetría (ssh/subprocess) activo; fork
# con hilos vivos deadlock-ea el pool (ver job 010f7f82 / worker_dump.txt).
_MP_SPAWN = multiprocessing.get_context("spawn")
_pool: ProcessPoolExecutor | None = None
_pool_workers: int | None = None
_pool_lock = threading.Lock()


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


def _shared_pool(workers: int) -> ProcessPoolExecutor:
    """Un solo pool spawn: recrearlo por política haría cada ronda mucho más lenta."""
    global _pool, _pool_workers
    with _pool_lock:
        if _pool is None or _pool_workers != workers:
            if _pool is not None:
                _pool.shutdown(wait=True)
            _pool = ProcessPoolExecutor(max_workers=workers, mp_context=_MP_SPAWN)
            _pool_workers = workers
        return _pool


def shutdown_pool() -> None:
    """Cierra el pool compartido. Los tests pueden llamarlo para no dejar workers vivos."""
    global _pool, _pool_workers
    with _pool_lock:
        if _pool is not None:
            _pool.shutdown(wait=True)
            _pool = None
            _pool_workers = None


atexit.register(shutdown_pool)


def simulate_many(
    policy: Policy | dict,
    seeds: list[int] | tuple[int, ...],
    workers: int,
    config: PlantConfig | None = None,
    scenario: Scenario = "base",
) -> list[dict[str, float]]:
    """Misma política en varias semillas. workers>1 usa ProcessPoolExecutor (spawn)."""
    seed_list = [int(seed) for seed in seeds]
    if workers <= 1 or len(seed_list) <= 1:
        return [simulate(policy, seed, config, scenario) for seed in seed_list]
    jobs = [(policy, seed, config, scenario) for seed in seed_list]
    return list(_shared_pool(workers).map(_simulate_job, jobs))
