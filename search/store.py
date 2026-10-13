"""Persiste una búsqueda para poder reconstruir la curva sin volver a llamar al LLM."""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import MetricRow, PolicyRow, RunEvent, SearchRun, utcnow
from search.loop import EvaluatedPolicy, SearchResult, result_payload


def policy_hash(policy_json: dict) -> str:
    body = json.dumps(policy_json, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


def _insert_policy(
    session: Session,
    job_id: uuid.UUID,
    item: EvaluatedPolicy,
    seed_set: str,
) -> uuid.UUID:
    body = item.policy_json()
    source = item.source if item.source in {"fixed", "llm", "optuna", "llm_no_feedback"} else "llm"
    stored = PolicyRow(
        job_id=job_id,
        round=item.round,
        source=source,
        policy_json=body,
        valid=True,
    )
    session.add(stored)
    session.flush()
    session.add(
        MetricRow(
            policy_id=stored.id,
            seed_set=seed_set,
            n_seeds=item.n_seeds,
            objective=item.objective,
            kpis=item.kpis,
            ci_low=item.ci_low,
            ci_high=item.ci_high,
            sims_spent=item.n_seeds,
        )
    )
    return stored.id


def persist_search(
    session: Session,
    job_id: uuid.UUID,
    result: SearchResult,
    *,
    model: str,
    config: dict,
) -> SearchRun:
    """Guarda la corrida. Si el job ya tenía una hecha, esa queda superseded."""
    started = utcnow()
    previous = session.scalars(
        select(SearchRun).where(
            SearchRun.job_id == job_id,
            SearchRun.status.in_(("done", "running")),
        )
    ).all()
    for row in previous:
        row.status = "superseded"
    ids: list[uuid.UUID] = []
    best_policy_id = None
    for item in result.policies:
        stored_id = _insert_policy(session, job_id, item, "train")
        ids.append(stored_id)
        if item.policy is result.best_policy and item.objective == result.best_objective:
            best_policy_id = stored_id
    if result.holdout is not None and best_policy_id is not None:
        session.add(
            MetricRow(
                policy_id=best_policy_id,
                seed_set="holdout",
                n_seeds=result.holdout.n_seeds,
                objective=result.holdout.objective,
                kpis=result.holdout.kpis,
                ci_low=result.holdout.ci_low,
                ci_high=result.holdout.ci_high,
                sims_spent=result.holdout.n_seeds,
            )
        )
    for item in result.rounds:
        valid = [policy.model_dump(mode="json", by_alias=True) for policy in item.valid]
        session.add(
            RunEvent(
                job_id=job_id,
                seq=100 + item.round,
                event_type="round",
                payload={
                    "prompt": item.prompt,
                    "valid": valid,
                    "invalid": item.invalid,
                    "latencies_s": item.latencies_s,
                    "sims_spent": item.sims_spent,
                    "objectives": [scored.objective for scored in item.evaluated],
                    "hashes": [policy_hash(body) for body in valid],
                },
                created_at=utcnow(),
            )
        )
    if best_policy_id is None and ids:
        best_policy_id = ids[0]
    run = SearchRun(
        job_id=job_id,
        status="done",
        started_at=started,
        finished_at=utcnow(),
        config=config,
        total_simulations=result.simulations_total,
        best_policy_id=best_policy_id,
        best_objective=result.best_objective,
        raw_json=result_payload(result, model),
    )
    session.add(run)
    session.flush()
    return run


def latest_done(session: Session) -> SearchRun | None:
    return session.scalars(
        select(SearchRun)
        .where(SearchRun.status == "done")
        .order_by(SearchRun.finished_at.desc(), SearchRun.id.desc())
    ).first()


def format_last(run: SearchRun | None) -> str:
    if run is None:
        return "no hay corridas"
    return (
        f"best_objective={run.best_objective} total_simulations={run.total_simulations} "
        f"job_id={run.job_id}"
    )
