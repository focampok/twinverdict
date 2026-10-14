"""Línea base Optuna (TPE) con el mismo presupuesto de simulaciones que el bucle.

Optuna solo ajusta parámetros de una Policy válida: nunca genera código ni reglas
condicionales. `rules` va vacía a propósito. Esa es la ventaja estructural del LLM
frente a esta línea base, y conviene decirlo al lado de los números: si aquí sale
mejor, el bucle con retroalimentación no aportó.

El trial 0 es la regla fija (study.enqueue_trial), igual que la política 0 del
bucle, y sus K simulaciones cuentan en el presupuesto.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import optuna
from pydantic import ValidationError

from baselines.budget import total_train_sims, train_seeds
from config import Settings
from policy.schema import MACHINES, Dispatch, Maintenance, Policy
from search.config import SearchConfig
from search.loop import SearchResult, evaluate_policy
from search.repro import build_search_config
from sim.runner import Scenario

# Rangos tomados de los validadores de policy/schema.py, no inventados.
PM_MIN = 0.30
PM_MAX = 0.95
MAX_PM_MIN = 0
MAX_PM_MAX = 3
DISPATCH_RULES = ("EDD", "SPT", "WEIGHTED", "CRITICAL_RATIO")

# El trial 0 reproduce fixed_rule_policy(): EDD, umbral 0.75, un PM por turno.
# Los pesos van aunque EDD no los use: Optuna exige sugerir lo mismo en cada trial.
FIXED_PARAMS: dict[str, float | int | str] = {
    **{f"pm_{machine}": 0.75 for machine in MACHINES},
    "max_pm_per_shift": 1,
    "dispatch_rule": "EDD",
    "w_due_date": 1 / 3,
    "w_wear_risk": 1 / 3,
    "w_setup": 1 / 3,
}

optuna.logging.set_verbosity(optuna.logging.WARNING)


@dataclass(slots=True)
class OptunaResult:
    best_policy: Policy
    best_objective: float
    fixed_objective: float
    simulations_total: int
    history: list[dict[str, float | int]]
    trials: int
    failed_trials: int
    sim_workers: int
    seconds_per_sim: float
    train_seeds: list[int]
    seed: int
    scenario: Scenario


def suggest_params(trial: optuna.Trial) -> dict[str, float | int | str]:
    """Espacio de búsqueda. Siempre los mismos suggest, en el mismo orden."""
    params: dict[str, float | int | str] = {}
    for machine in MACHINES:
        params[f"pm_{machine}"] = trial.suggest_float(f"pm_{machine}", PM_MIN, PM_MAX)
    params["max_pm_per_shift"] = trial.suggest_int("max_pm_per_shift", MAX_PM_MIN, MAX_PM_MAX)
    params["dispatch_rule"] = trial.suggest_categorical("dispatch_rule", list(DISPATCH_RULES))
    params["w_due_date"] = trial.suggest_float("w_due_date", 0.0, 1.0)
    params["w_wear_risk"] = trial.suggest_float("w_wear_risk", 0.0, 1.0)
    params["w_setup"] = trial.suggest_float("w_setup", 0.0, 1.0)
    return params


def policy_from_params(params: dict[str, float | int | str]) -> Policy:
    """Construye la Policy y la valida. Si no valida, el trial no gasta simulaciones.

    Los pesos se pasan sin normalizar: Dispatch los normaliza a suma 1 al validar,
    así que la suma 1 sale del schema y no de una segunda regla aquí.
    """
    rule = str(params["dispatch_rule"])
    dispatch: dict = {"rule": rule}
    if rule == "WEIGHTED":
        dispatch["weights"] = {
            "due_date": params["w_due_date"],
            "wear_risk": params["w_wear_risk"],
            "setup": params["w_setup"],
        }
    return Policy(
        maintenance=Maintenance(
            pm_wear_threshold={machine: params[f"pm_{machine}"] for machine in MACHINES},
            max_pm_per_shift=int(params["max_pm_per_shift"]),
        ),
        dispatch=Dispatch(**dispatch),
        rules=[],
    )


def _completed(study: optuna.Study) -> list[optuna.trial.FrozenTrial]:
    return [trial for trial in study.trials if trial.value is not None]


def _history(study: optuna.Study, k_seeds: int) -> list[dict[str, float | int]]:
    """Curva acumulada: simulaciones gastadas y mejor objetivo hasta ese trial."""
    rows: list[dict[str, float | int]] = []
    cumulative = 0
    best_so_far = float("-inf")
    for trial in _completed(study):
        cumulative += k_seeds
        best_so_far = max(best_so_far, float(trial.value))
        rows.append(
            {
                "trial": trial.number,
                "sims_acumuladas": cumulative,
                "objetivo": float(trial.value),
                "best_so_far": best_so_far,
            }
        )
    return rows


def run_optuna(
    config: SearchConfig,
    scenario: Scenario,
    rng_seed: int,
    workers: int | None = None,
) -> OptunaResult:
    """maximiza el objetivo medio en las K semillas de entrenamiento del bucle."""
    pool_workers = Settings().SIM_WORKERS if workers is None else workers
    seeds = train_seeds(config, rng_seed)
    target_trials = total_train_sims(config) // config.K

    study = optuna.create_study(
        direction="maximize", sampler=optuna.samplers.TPESampler(seed=rng_seed)
    )
    study.enqueue_trial(FIXED_PARAMS)

    sims = 0
    sim_seconds = 0.0
    fixed_objective: float | None = None

    def objective(trial: optuna.Trial) -> float:
        nonlocal sims, sim_seconds, fixed_objective
        policy = policy_from_params(suggest_params(trial))  # inválida: no gasta nada
        started = time.perf_counter()
        scored = evaluate_policy(policy, seeds, pool_workers, scenario, "optuna", trial.number)
        sim_seconds += time.perf_counter() - started
        sims += config.K
        if trial.number == 0:
            fixed_objective = scored.objective
        return scored.objective

    # Un trial inválido no gasta simulaciones, así que se repone hasta completar el
    # presupuesto. El tope evita un bucle infinito si todo el espacio fuese inválido.
    max_trials = target_trials * 2
    while len(_completed(study)) < target_trials and len(study.trials) < max_trials:
        pending = target_trials - len(_completed(study))
        study.optimize(objective, n_trials=pending, catch=(ValidationError,))

    done = _completed(study)
    if not done or fixed_objective is None:
        raise RuntimeError(f"Optuna no completó ningún trial válido ({len(study.trials)} intentos)")

    best = study.best_trial
    return OptunaResult(
        best_policy=policy_from_params(best.params),
        best_objective=float(study.best_value),
        fixed_objective=fixed_objective,
        simulations_total=sims,
        history=_history(study, config.K),
        trials=len(done),
        failed_trials=len(study.trials) - len(done),
        sim_workers=pool_workers,
        seconds_per_sim=sim_seconds / sims if sims else 0.0,
        train_seeds=seeds,
        seed=rng_seed,
        scenario=scenario,
    )


def result_payload(config: SearchConfig, result: OptunaResult) -> dict:
    """Mismo formato y metadatos que una búsqueda, con modelo "none": aquí no hay LLM."""
    as_search = SearchResult(
        policies=[],
        rounds=[],
        simulations_total=result.simulations_total,
        best_policy=result.best_policy,
        best_objective=result.best_objective,
        fixed_objective=result.fixed_objective,
        holdout_objective=None,
        holdout=None,
        seed=result.seed,
        scenario=result.scenario,
        train_seeds=result.train_seeds,
        holdout_seeds=[],
        sim_workers=result.sim_workers,
        seconds_per_sim=result.seconds_per_sim,
    )
    return {
        "method": "optuna_tpe",
        "best_policy": result.best_policy.model_dump(mode="json", by_alias=True),
        "best_objective": result.best_objective,
        "fixed_objective": result.fixed_objective,
        "simulations_total": result.simulations_total,
        "trials": result.trials,
        "failed_trials": result.failed_trials,
        "history": result.history,
        "config": build_search_config(config, as_search, "none"),
    }


def write_result(config: SearchConfig, result: OptunaResult, directory: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    path = directory / f"optuna_{config.profile}_seed{result.seed}_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_payload(config, result), indent=2) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Línea base Optuna (TPE), presupuesto igual")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scenario", default="base", choices=("base", "stress"))
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("bench/results"))
    args = parser.parse_args()

    config = SearchConfig.from_profile(args.profile)
    started = time.perf_counter()
    result = run_optuna(config, args.scenario, args.seed, workers=args.workers)
    path = write_result(config, result, args.out)
    minutes = (time.perf_counter() - started) / 60.0
    print(
        f"optuna {args.profile} seed={args.seed}: mejor={result.best_objective:.4f} "
        f"fija={result.fixed_objective:.4f} sims={result.simulations_total} "
        f"trials={result.trials} fallidos={result.failed_trials} "
        f"{minutes:.1f} min json={path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
