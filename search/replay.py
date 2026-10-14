"""Carga una corrida persistida para replay: sin LLM y sin simulación.

`load_replay(job_id)` lee de Postgres todo lo que dejó una búsqueda y lo devuelve en un
diccionario estable, listo para que la UI del jueves solo lea datos. Nada de aquí vuelve a
llamar al modelo ni al simulador.

Si el job corrió por el worker, hay `search_runs` con las rondas en `runs`, las políticas en
`policies` y las métricas de entrenamiento, holdout y estrés en `metrics`. Las líneas base del
miércoles (Optuna y LLM sin retroalimentación) no viven en la base: se enlazan por convención
de nombre de archivo en `bench/results`, que es donde su corrida las dejó.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Job, MetricRow, PolicyRow, RunEvent, SearchRun
from db.session import session_factory
from eval.efficiency import curve

RESULTS_DIR = Path("bench/results")

# Nombre de archivo de cada línea base, con el perfil y la semilla de la corrida.
BASELINE_PATTERNS = {
    "optuna": "optuna_{profile}_seed{seed}_*.json",
    "llm_no_feedback": "llm_nofeedback_{profile}_seed{seed}_*.json",
}


def _latest(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime)
    return matches[-1] if matches else None


def replay_curve(rounds: list[dict[str, Any]], fixed_objective: float, k: int) -> list[list[float]]:
    """Mejor objetivo contra simulaciones, desde las rondas ya persistidas.

    Una ronda propone las N candidatas juntas, así que la granularidad es la ronda: es la
    misma convención que usa `eval/efficiency.py`.
    """
    history: list[dict[str, float]] = [{"sims_acumuladas": k, "best_so_far": fixed_objective}]
    sims = k
    best = fixed_objective
    for payload in rounds:
        for objective in payload.get("objectives") or []:
            best = max(best, float(objective))
        sims += int(payload.get("sims_spent") or 0)
        history.append({"sims_acumuladas": sims, "best_so_far": best})
    return [[int(sims), float(best)] for sims, best in curve(history)]


def _metrics(session: Session, policy_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    rows = session.scalars(select(MetricRow).where(MetricRow.policy_id == policy_id)).all()
    return {
        row.seed_set: {
            "n_seeds": row.n_seeds,
            "objective": row.objective,
            "kpis": row.kpis,
            "ci_low": row.ci_low,
            "ci_high": row.ci_high,
            "sims_spent": row.sims_spent,
        }
        for row in rows
    }


def _baselines(config: dict[str, Any], directory: Path) -> dict[str, dict[str, Any] | None]:
    """Enlace a las líneas base por perfil y semilla. No están en la base, viven en JSON."""
    profile = config.get("profile")
    seed = config.get("seed")
    linked: dict[str, dict[str, Any] | None] = {}
    for name, pattern in BASELINE_PATTERNS.items():
        path = None
        if isinstance(profile, str) and seed is not None:
            path = _latest(directory, pattern.format(profile=profile, seed=seed))
        if path is None:
            linked[name] = None
            continue
        payload = json.loads(path.read_text())
        linked[name] = {
            "path": str(path),
            "method": payload.get("method"),
            "best_objective": payload.get("best_objective"),
            "fixed_objective": payload.get("fixed_objective"),
            "simulations_total": payload.get("simulations_total"),
            "llm_source": (payload.get("config") or {}).get("llm_source"),
        }
    return linked


def _build(session: Session, job_id: uuid.UUID, directory: Path) -> dict[str, Any]:
    job = session.get(Job, job_id)
    if job is None:
        raise SystemExit(f"no existe el job {job_id}")
    run = session.scalars(
        select(SearchRun)
        .where(SearchRun.job_id == job_id)
        .order_by(SearchRun.finished_at.desc().nullslast(), SearchRun.id.desc())
    ).first()
    if run is None:
        raise SystemExit(f"el job {job_id} no tiene corrida persistida: nada que repetir")

    events = session.scalars(
        select(RunEvent).where(RunEvent.job_id == job_id).order_by(RunEvent.seq)
    ).all()
    rounds = [
        {**dict(event.payload), "seq": event.seq} for event in events if event.event_type == "round"
    ]
    stored = session.scalars(
        select(PolicyRow).where(PolicyRow.job_id == job_id).order_by(PolicyRow.round, PolicyRow.id)
    ).all()
    policies = [
        {
            "id": str(row.id),
            "round": row.round,
            "source": row.source,
            "valid": row.valid,
            "policy": row.policy_json,
            "metrics": _metrics(session, row.id),
        }
        for row in stored
    ]
    config = dict(run.config or {})
    by_id = {item["id"]: item for item in policies}
    best = by_id.get(str(run.best_policy_id)) if run.best_policy_id else None
    fixed = next((item for item in policies if item["source"] == "fixed"), None)
    holdout_seeds = config.get("holdout_seeds") or []
    # La curva arranca en la política 0: la regla fija evaluada en K semillas, NO el mejor
    # objetivo de la corrida. Confundirlos pondría el techo al principio de la curva.
    fixed_train = ((fixed or {}).get("metrics") or {}).get("train") or {}
    fixed_objective = float(fixed_train.get("objective", 0.0))
    k = int(config.get("K") or 0)
    return {
        "job": {
            "id": str(job.id),
            "kind": job.kind,
            "status": job.status,
            "params": dict(job.params or {}),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error": job.error,
        },
        "config": config,
        "run": {
            "id": str(run.id),
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "total_simulations": run.total_simulations,
            "best_objective": run.best_objective,
            "best_policy_id": str(run.best_policy_id) if run.best_policy_id else None,
        },
        "rounds": rounds,
        "policies": policies,
        "best_policy": None if best is None else best["policy"],
        "best_metrics": {} if best is None else best["metrics"],
        "fixed_policy": None if fixed is None else fixed["policy"],
        "fixed_metrics": {} if fixed is None else fixed["metrics"],
        "curve": replay_curve(rounds, fixed_objective, k) if rounds else [],
        "baselines": _baselines(config, directory),
        "events": [{"seq": e.seq, "type": e.event_type, "payload": e.payload} for e in events],
        "holdout_seeds": holdout_seeds,
    }


def load_replay(
    job_id: uuid.UUID | str,
    session: Session | None = None,
    directory: Path = RESULTS_DIR,
) -> dict[str, Any]:
    """Diccionario estable de la corrida. Con `session` no abre ni cierra una propia."""
    key = uuid.UUID(str(job_id))
    if session is not None:
        return _build(session, key, directory)
    factory = session_factory()
    with factory() as own:
        return _build(own, key, directory)


def _kpi(metrics: dict[str, Any], seed_set: str, key: str) -> float | None:
    block = metrics.get(seed_set)
    if not block:
        return None
    kpis = block.get("kpis") or {}
    return None if key not in kpis else float(kpis[key])


def _summary(policy: dict[str, Any]) -> dict[str, Any]:
    maintenance = policy["maintenance"]
    dispatch = policy["dispatch"]
    thresholds = {
        machine: float(value) for machine, value in maintenance["pm_wear_threshold"].items()
    }
    values = sorted(thresholds.values())
    return {
        "dispatch_rule": dispatch["rule"],
        "dispatch_weights": dispatch.get("weights"),
        "max_pm_per_shift": maintenance["max_pm_per_shift"],
        "pm_wear_threshold": thresholds,
        "rules": len(policy.get("rules") or []),
        "texto": (
            f"Despacho {dispatch['rule']}, hasta {maintenance['max_pm_per_shift']} "
            f"mantenimientos por turno y umbrales de desgaste entre "
            f"{values[0]:.2f} y {values[-1]:.2f}"
            if values
            else f"Despacho {dispatch['rule']} con umbral por defecto"
        ),
    }


def _numbers(replay: dict[str, Any]) -> dict[str, float]:
    """Todos los números de la tarjeta, en plano. Cada uno sale de la base."""
    fixed = replay["fixed_metrics"]
    best = replay["best_metrics"]
    numbers: dict[str, float] = {
        "simulations_total": float(replay["run"]["total_simulations"]),
        "n_seeds_train": float((fixed.get("train") or {}).get("n_seeds", 0)),
        "n_seeds_holdout": float((fixed.get("holdout") or {}).get("n_seeds", 0)),
    }
    for label, metrics in (("fixed", fixed), ("best", best)):
        for seed_set in ("train", "holdout", "stress"):
            block = metrics.get(seed_set)
            if not block:
                continue
            numbers[f"objective_{label}_{seed_set}"] = float(block["objective"])
            numbers[f"objective_{label}_{seed_set}_ci_low"] = float(block["ci_low"])
            numbers[f"objective_{label}_{seed_set}_ci_high"] = float(block["ci_high"])
            for key in (
                "on_time_rate",
                "throughput",
                "unplanned_downtime_h",
                "planned_downtime_h",
                "maintenance_cost",
                "pm_count",
                "failures_total",
            ):
                value = _kpi(metrics, seed_set, key)
                if value is not None:
                    numbers[f"{key}_{label}_{seed_set}"] = value
    for seed_set in ("train", "holdout", "stress"):
        fixed_on_time = numbers.get(f"on_time_rate_fixed_{seed_set}")
        best_on_time = numbers.get(f"on_time_rate_best_{seed_set}")
        if fixed_on_time is not None and best_on_time is not None:
            numbers[f"delta_on_time_{seed_set}"] = best_on_time - fixed_on_time
        fixed_throughput = numbers.get(f"throughput_fixed_{seed_set}")
        best_throughput = numbers.get(f"throughput_best_{seed_set}")
        if fixed_throughput is not None and best_throughput is not None:
            numbers[f"delta_throughput_{seed_set}"] = best_throughput - fixed_throughput
    if replay["best_policy"] is not None:
        summary = _summary(replay["best_policy"])
        numbers["best_max_pm_per_shift"] = float(summary["max_pm_per_shift"])
        numbers["best_rules"] = float(summary["rules"])
        for machine, value in summary["pm_wear_threshold"].items():
            numbers[f"best_threshold_{machine}"] = float(value)
    return numbers


def operator_card(replay: dict[str, Any]) -> dict[str, Any]:
    """Snapshot de la tarjeta de operador. Solo números medidos, sin texto del LLM."""
    best = replay["best_metrics"]
    fixed = replay["fixed_metrics"]
    holdout = best.get("holdout") or {}
    numbers = _numbers(replay)
    card: dict[str, Any] = {
        "job_id": replay["job"]["id"],
        "generated_from": {
            "profile": replay["config"].get("profile"),
            "seed": replay["config"].get("seed"),
            "scenario": replay["config"].get("scenario"),
            "N": replay["config"].get("N"),
            "K": replay["config"].get("K"),
            "R": replay["config"].get("R"),
            "model": replay["config"].get("model"),
            "llm_source": replay["config"].get("llm_source"),
            "git_commit": replay["config"].get("git_commit"),
            "train_seeds": replay["config"].get("train_seeds"),
            "holdout_seeds": replay["config"].get("holdout_seeds"),
        },
        "fixed": {
            "train": fixed.get("train"),
            "holdout": fixed.get("holdout"),
            "stress": fixed.get("stress"),
        },
        "best": {
            "train": best.get("train"),
            "holdout": best.get("holdout"),
            "stress": best.get("stress"),
        },
        "objective_holdout": {
            "fixed": None if not fixed.get("holdout") else fixed["holdout"]["objective"],
            "best": holdout.get("objective"),
            "best_ci_low": holdout.get("ci_low"),
            "best_ci_high": holdout.get("ci_high"),
            "fixed_ci_low": None if not fixed.get("holdout") else fixed["holdout"]["ci_low"],
            "fixed_ci_high": None if not fixed.get("holdout") else fixed["holdout"]["ci_high"],
        },
        "winning_policy": None
        if replay["best_policy"] is None
        else _summary(replay["best_policy"]),
        "stress_note": (
            "En estrés (+30% fallas, demanda x1.5) las dos políticas empeoran y el hueco lo "
            "lleva el throughput, no el % a tiempo, así que la tarjeta no promete el mismo "
            "salto bajo ese pico."
        ),
        "numbers": numbers,
    }
    return card
