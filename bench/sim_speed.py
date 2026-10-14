"""Segundos por simulación, en serie y en paralelo, y cupo para una búsqueda."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from policy.schema import fixed_rule_policy
from sim.runner import simulate, simulate_many

SEARCH_SIMS = 100 * 32 * 8  # K * N * R = 25_600
BUDGET_MIN = 25.0


def _percentile(samples: list[float], q: float) -> float:
    ordered = sorted(samples)
    index = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[index]


def _print_stats(label: str, samples: list[float]) -> tuple[float, float]:
    mean = statistics.fmean(samples)
    p95 = _percentile(samples, 0.95)
    print(f"{label}: media {mean:.4f} s  p95 {p95:.4f} s")
    return mean, p95


def main() -> None:
    parser = argparse.ArgumentParser(description="Velocidad del simulador")
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Tandas paralelas. Con más de una, el s/sim del JSON es la media desde la segunda.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Ruta del JSON. Por defecto bench/results/sim_speed_<fecha>.json",
    )
    args = parser.parse_args()
    if args.repeat < 1:
        raise SystemExit("--repeat debe ser >= 1")
    policy = fixed_rule_policy()
    seeds = list(range(args.seeds))

    serial_times: list[float] = []
    for seed in seeds:
        metrics = simulate(policy, seed)
        serial_times.append(metrics["sim_wall_s"])
    serial_mean, serial_p95 = _print_stats("serie", serial_times)

    effective_runs: list[float] = []
    parallel_metrics: list[dict[str, float]] = []
    parallel_wall = 0.0
    for index in range(args.repeat):
        started = time.perf_counter()
        parallel_metrics = simulate_many(policy, seeds, args.workers)
        parallel_wall = time.perf_counter() - started
        run_effective = parallel_wall / max(1, len(seeds))
        effective_runs.append(run_effective)
        if args.repeat > 1:
            print(
                f"tanda {index + 1}/{args.repeat}: {parallel_wall:.3f} s, "
                f"{run_effective:.4f} s por simulación"
            )
    parallel_each = [row["sim_wall_s"] for row in parallel_metrics]
    parallel_mean, parallel_p95 = _print_stats(
        f"paralelo ({args.workers} workers, tiempo dentro del proceso)",
        parallel_each,
    )
    burst = effective_runs[0]
    sustained = statistics.fmean(effective_runs[1:] or effective_runs)
    effective = sustained if args.repeat > 1 else burst
    print(f"paralelo pared: {parallel_wall:.3f} s totales, {burst:.4f} s por simulación")
    if args.repeat > 1:
        print(
            f"sostenido (tandas 2-{args.repeat}): {sustained:.4f} s por simulación "
            f"({args.workers} workers)"
        )
    fit = int(BUDGET_MIN * 60.0 / effective) if effective > 0 else 0
    search_s = SEARCH_SIMS * effective
    print(f"en {BUDGET_MIN:.0f} min caben {fit} simulaciones (usando el tiempo de pared paralelo)")
    print(
        f"búsqueda K=100 N=32 R=8 ({SEARCH_SIMS} sims) "
        f"tardaría {search_s / 60.0:.2f} min en este paralelo"
    )
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    json_path = args.json or Path("bench/results") / f"sim_speed_{stamp}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seeds": args.seeds,
        "workers": args.workers,
        "serial_mean_s": serial_mean,
        "serial_p95_s": serial_p95,
        "parallel_mean_s": parallel_mean,
        "parallel_p95_s": parallel_p95,
        "parallel_wall_s": parallel_wall,
        "parallel_effective_s": effective,
        "repeat": args.repeat,
        "burst_effective_s": burst,
        "sustained_effective_s": sustained,
        "search_sims": SEARCH_SIMS,
        "search_minutes": search_s / 60.0,
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"json: {json_path}")


if __name__ == "__main__":
    main()
