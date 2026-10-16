"""Probador de políticas: el usuario arma una política y el simulador la compara.

No llama al LLM ni a la cola de jobs. Las tres políticas corren sobre las mismas semillas
del holdout de la corrida congelada, en la planta calibrada.
"""

from __future__ import annotations

import asyncio
import json
import math
import multiprocessing
import statistics
import time
import uuid
from collections import deque
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from pydantic import ValidationError

from api.operator import load_replay
from policy.schema import MACHINES, Policy, fixed_rule_policy, parse_policy
from sim.calibration import calibrated_plant_config
from sim.config import PlantConfig
from sim.objective import composite_objective
from sim.record import record_policy
from sim.runner import _simulate_job

TRY_SEED_COUNT = 20
GANTT_SEED = 1_000_111
TIMEOUT_S = 20.0
RATE_LIMIT = 6
RATE_WINDOW_S = 60.0
WEIGHT_KEYS = ("due_date", "wear_risk", "setup")


class TryPolicyError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def validation_message(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        where = ".".join(str(item) for item in error["loc"]) or "policy"
        parts.append(f"{where}: {error['msg']}")
    return "; ".join(parts)


def validate_policy(raw: object) -> Policy:
    if not isinstance(raw, dict):
        raise TryPolicyError(422, "policy must be a JSON object")
    try:
        return parse_policy(raw)
    except ValidationError as exc:
        raise TryPolicyError(422, validation_message(exc)) from None


def _number(form: Mapping[str, str], key: str, cast: type[float] | type[int]) -> float | int:
    raw = form.get(key)
    if raw is None or raw == "":
        raise TryPolicyError(422, f"{key} is missing")
    try:
        return cast(raw)
    except ValueError:
        raise TryPolicyError(422, f"{key} is not a number: {raw!r}") from None


def policy_from_form(form: Mapping[str, str]) -> dict[str, Any]:
    """Campos del formulario de la UI a un dict de política. La validación es del esquema."""
    rules_raw = form.get("rules") or "[]"
    try:
        rules = json.loads(rules_raw)
    except json.JSONDecodeError:
        raise TryPolicyError(422, "rules is not valid JSON") from None
    return {
        "maintenance": {
            "pm_wear_threshold": {
                machine: _number(form, f"pm_{machine}", float) for machine in MACHINES
            },
            "max_pm_per_shift": _number(form, "max_pm_per_shift", int),
        },
        "dispatch": {
            "rule": form.get("rule", ""),
            "weights": {key: _number(form, f"w_{key}", float) for key in WEIGHT_KEYS},
        },
        "rules": rules,
    }


def controls(policy: Policy) -> dict[str, Any]:
    """Valores con los que la UI prellena sus controles."""
    weights = policy.dispatch.weights
    assert weights is not None
    return {
        "rule": policy.dispatch.rule,
        "weights": {key: getattr(weights, key) for key in WEIGHT_KEYS},
        "thresholds": {machine: policy.maintenance.threshold_for(machine) for machine in MACHINES},
        "max_pm_per_shift": policy.maintenance.max_pm_per_shift,
        "rules": [rule.model_dump(by_alias=True, mode="json") for rule in policy.rules],
    }


def summarize(rows: list[dict[str, float]]) -> dict[str, float]:
    """Medias por semilla. IC 95% normal del objetivo, igual que la búsqueda."""
    objectives = [composite_objective(row) for row in rows]
    mean = statistics.fmean(objectives)
    margin = 0.0
    if len(objectives) > 1:
        margin = 1.96 * statistics.stdev(objectives) / math.sqrt(len(objectives))
    return {
        "on_time_rate": statistics.fmean(row["on_time_rate"] for row in rows),
        "unplanned_min": statistics.fmean(row["unplanned_downtime_h"] * 60.0 for row in rows),
        "objective": mean,
        "objective_ci_low": mean - margin,
        "objective_ci_high": mean + margin,
    }


def _compact(record: dict[str, Any]) -> dict[str, Any]:
    intervals = [
        {
            "m": row["m"],
            "start": round(row["start"], 2),
            "end": round(row["end"], 2),
            "kind": row["kind"],
        }
        for row in record["intervals"]
    ]
    kpis = record["kpis"]
    return {
        "kpis": {"on_time": kpis["on_time"], "unplanned_min": kpis["unplanned_min"]},
        "intervals": intervals,
    }


class RateLimiter:
    """Ventana deslizante en memoria por clave. Se pierde al reiniciar, a propósito."""

    def __init__(self, limit: int = RATE_LIMIT, window_s: float = RATE_WINDOW_S) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        hits = self._hits.setdefault(key, deque())
        while hits and moment - hits[0] >= self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(moment)
        return True


def reference_policies(job_id: str) -> tuple[Policy, Policy, list[int], int]:
    """Regla fija, best_policy del replay y las primeras semillas de su holdout."""
    replay = load_replay(uuid.UUID(job_id))
    best = replay.get("best_policy")
    if not isinstance(best, dict):
        raise ValueError(f"replay {job_id} has no best_policy")
    holdout = [int(seed) for seed in replay["config"]["holdout_seeds"]]
    return fixed_rule_policy(), parse_policy(best), holdout[:TRY_SEED_COUNT], len(holdout)


_REFERENCES: dict[tuple[str, PlantConfig], dict[str, Any]] = {}


class PolicyLab:
    """ProcessPool propio, creado al primer uso. Las referencias se cachean por proceso."""

    def __init__(self, job_id: str, workers: int, config: PlantConfig | None = None) -> None:
        self.job_id = job_id
        self.workers = max(1, workers)
        self.config = calibrated_plant_config() if config is None else config
        self.fixed, self.llm, self.seeds, self.official_seeds = reference_policies(job_id)
        self._pool: ProcessPoolExecutor | None = None

    def _executor(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(
                max_workers=self.workers, mp_context=multiprocessing.get_context("spawn")
            )
        return self._pool

    async def evaluate(self, policy: Policy) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        pool = self._executor()
        futures = [
            loop.run_in_executor(pool, _simulate_job, (policy, seed, self.config, "base"))
            for seed in self.seeds
        ]
        gantt = loop.run_in_executor(pool, record_policy, GANTT_SEED, policy, self.config)
        try:
            *rows, recorded = await asyncio.gather(*futures, gantt)
        except asyncio.CancelledError:
            for future in (*futures, gantt):
                future.cancel()
            raise
        return {"summary": summarize(rows), "gantt": _compact(recorded)}

    async def references(self) -> dict[str, Any]:
        key = (self.job_id, self.config)
        if key not in _REFERENCES:
            fixed, llm = await asyncio.gather(self.evaluate(self.fixed), self.evaluate(self.llm))
            _REFERENCES[key] = {"fixed": fixed, "llm": llm}
        return _REFERENCES[key]

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None
