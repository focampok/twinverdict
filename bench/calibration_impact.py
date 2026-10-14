"""Impacto de calibrar la curva desgaste → riesgo: misma política, dos PlantConfig.

Compara la regla fija y la mejor política de una búsqueda, en las mismas semillas, con
la forma de antes del corte (midpoint 0.72, steepness 14) y con la de ahora, que es el
default. Lo único que cambia entre las dos columnas es `failure_midpoint` y
`failure_steepness`.

Las semillas son las de holdout, las que no vio ninguna búsqueda, para que el número sea
comparable con el % a tiempo de la tarjeta de operador.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from config import Settings
from eval.efficiency import holdout_seeds
from policy.schema import Policy, fixed_rule_policy, parse_policy
from search.config import SearchConfig
from sim.calibration import PRE_CUT_MIDPOINT, PRE_CUT_STEEPNESS
from sim.config import PlantConfig
from sim.objective import composite_objective, load_objective_weights
from sim.runner import simulate_many


def _latest(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise SystemExit(f"no hay archivos {pattern} en {directory}")
    return matches[-1]


def evaluate(policy: Policy, config: PlantConfig, seeds: list[int], workers: int) -> dict:
    rows = simulate_many(policy, seeds, workers, config, scenario="base")
    weights = load_objective_weights()
    scores = [composite_objective(row, weights) for row in rows]
    return {
        "objective": float(np.mean(scores)),
        "on_time_rate": float(np.mean([row["on_time_rate"] for row in rows])),
        "failures": float(np.mean([row["failures_total"] for row in rows])),
        "unplanned_downtime_h": float(np.mean([row["unplanned_downtime_h"] for row in rows])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Impacto de la calibración AI4I")
    parser.add_argument("--results-dir", type=Path, default=Path("bench/results"))
    parser.add_argument("--policy-json", type=Path, default=None)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    workers = Settings().SIM_WORKERS if args.workers is None else args.workers
    config = SearchConfig()
    seeds = holdout_seeds(config, 1)[: args.seeds]

    policy_path = args.policy_json or _latest(args.results_dir, "search_*.json")
    payload = json.loads(policy_path.read_text())
    policies = {
        "regla fija": fixed_rule_policy(),
        "mejor del bucle": parse_policy(payload["best_policy"]),
    }

    before = replace(
        PlantConfig(),
        failure_midpoint=PRE_CUT_MIDPOINT,
        failure_steepness=PRE_CUT_STEEPNESS,
    )
    calibrated = PlantConfig()
    print(f"semillas: {seeds[0]}..{seeds[-1]} ({len(seeds)})  workers={workers}")
    print(f"política: {policy_path.name}")
    print(
        f"midpoint/steepness: antes del corte {before.failure_midpoint}/{before.failure_steepness}"
        f"  corte {calibrated.failure_midpoint}/{calibrated.failure_steepness}"
    )
    header = (
        f"{'política':<18}{'config':<11}{'objetivo':>10}{'% a tiempo':>12}"
        f"{'fallas':>9}{'paro no plan. h':>17}"
    )
    print(header)
    for name, policy in policies.items():
        for label, plant in (("antes", before), ("corte", calibrated)):
            result = evaluate(policy, plant, seeds, workers)
            print(
                f"{name:<18}{label:<11}{result['objective']:>10.4f}"
                f"{100 * result['on_time_rate']:>11.1f}%{result['failures']:>9.2f}"
                f"{result['unplanned_downtime_h']:>17.4f}"
            )


if __name__ == "__main__":
    main()
