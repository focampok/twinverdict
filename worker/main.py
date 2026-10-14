"""Worker que reclama jobs con SKIP LOCKED. Corre baseline o una búsqueda."""

from __future__ import annotations

import asyncio
import math
import statistics
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings
from db.models import Job, MetricRow, PolicyRow, RunEvent, utcnow
from db.session import session_factory
from llm.client import LLMClient
from policy.schema import fixed_rule_policy
from search.config import PROFILES, SearchConfig
from search.loop import run_search
from search.repro import build_search_config
from search.store import persist_search
from sim.objective import composite_objective, load_objective_weights
from sim.runner import Scenario, simulate

BASELINE_SEEDS = 10


def _mean_kpis(rows: list[dict[str, float]]) -> dict[str, float]:
    keys = [key for key in rows[0] if key != "sim_wall_s"]
    count = float(len(rows))
    return {key: sum(row[key] for row in rows) / count for key in keys}


def _confidence(values: list[float]) -> tuple[float, float, float]:
    mean = statistics.fmean(values)
    if len(values) < 2:
        return mean, mean, mean
    margin = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return mean, mean - margin, mean + margin


def _event(session: Session, job_id: uuid.UUID, seq: int, event_type: str, payload: dict) -> None:
    session.add(
        RunEvent(
            job_id=job_id,
            seq=seq,
            event_type=event_type,
            payload=payload,
            created_at=utcnow(),
        )
    )


def _run_baseline(session: Session, job_id: uuid.UUID) -> None:
    policy = fixed_rule_policy()
    rows = [simulate(policy, seed) for seed in range(BASELINE_SEEDS)]
    weights = load_objective_weights()
    scores = [composite_objective(row, weights) for row in rows]
    objective, ci_low, ci_high = _confidence(scores)
    stored = PolicyRow(
        job_id=job_id,
        round=0,
        source="fixed",
        policy_json=policy.model_dump(mode="json", by_alias=True),
        valid=True,
    )
    session.add(stored)
    session.flush()
    session.add(
        MetricRow(
            policy_id=stored.id,
            seed_set="train",
            n_seeds=BASELINE_SEEDS,
            objective=objective,
            kpis=_mean_kpis(rows),
            ci_low=ci_low,
            ci_high=ci_high,
            sims_spent=BASELINE_SEEDS,
        )
    )
    _event(
        session,
        job_id,
        2,
        "metrics_saved",
        {"n_seeds": BASELINE_SEEDS, "objective": objective},
    )


def _search_config(params: dict) -> SearchConfig:
    name = params.get("profile")
    if isinstance(name, str) and name in PROFILES:
        config = SearchConfig.from_profile(name)
    else:
        config = SearchConfig()
    updates = {
        key: int(params[key])
        for key in ("N", "K", "R", "TOP_K")
        if key in params and params[key] is not None
    }
    if updates:
        return config.model_copy(update=updates)
    return config


def _run_search(session: Session, job_id: uuid.UUID) -> None:
    job = session.get(Job, job_id)
    assert job is not None
    params = dict(job.params or {})
    config = _search_config(params)
    scenario: Scenario = params.get("scenario", "base")
    seed = int(params.get("seed", 1))
    workers = int(params["workers"]) if params.get("workers") is not None else None
    holdout = int(params.get("holdout", 0))
    model = Settings().LLM_MODEL

    async def _go():
        client = LLMClient.from_settings(concurrency=max(1, config.N))
        try:
            return await run_search(
                config,
                client,
                scenario,
                seed,
                workers=workers,
                holdout_seeds=holdout,
            )
        finally:
            await client.aclose()

    result = asyncio.run(_go())
    repro = build_search_config(config, result, model)
    persist_search(
        session,
        job_id,
        result,
        model=model,
        config=repro,
    )
    stored = session.get(Job, job_id)
    assert stored is not None
    stored.params = {**dict(stored.params or {}), **repro}


def process_one(session: Session) -> bool:
    """Reclama un job queued. True si había trabajo."""
    job = session.scalars(
        select(Job)
        .where(Job.status == "queued")
        .order_by(Job.created_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        session.rollback()
        return False
    job_id = job.id
    kind = job.kind
    job.status = "running"
    job.started_at = utcnow()
    _event(session, job_id, 1, "claimed", {"kind": kind})
    session.commit()
    try:
        if kind == "baseline":
            _run_baseline(session, job_id)
        elif kind == "search":
            _run_search(session, job_id)
        else:
            raise RuntimeError(f"kind no soportado: {kind}")
        finished = session.get(Job, job_id)
        assert finished is not None
        finished.status = "done"
        finished.finished_at = utcnow()
        _event(session, job_id, 3, "done", {})
        session.commit()
        print(f"job {job_id} done", flush=True)
    except Exception as exc:
        session.rollback()
        failed = session.get(Job, job_id)
        assert failed is not None
        failed.status = "failed"
        failed.error = str(exc)
        failed.finished_at = utcnow()
        _event(session, job_id, 3, "failed", {"error": str(exc)})
        session.commit()
        print(f"job {job_id} failed: {exc}", flush=True)
    return True


def main() -> None:
    factory = session_factory()
    while True:
        with factory() as session:
            worked = process_one(session)
        if not worked:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
