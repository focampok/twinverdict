"""Presupuesto de una búsqueda a partir de los JSON de sim_speed y llm_throughput."""

from __future__ import annotations

import json
import os
from pathlib import Path

from search.config import SearchConfig

N_VALUES = (16, 32, 48)
K_VALUES = (30, 50, 100)
R_VALUES = (6, 8)


def latest(pattern: str, directory: Path = Path("bench/results")) -> Path:
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise SystemExit(f"no hay archivos {pattern} en {directory}")
    return matches[-1]


def _best_llm_row(payload: dict) -> dict:
    rows = payload["rows"]
    return max(rows, key=lambda row: float(row["valid_per_min"]))


def plan(
    sim_payload: dict,
    llm_payload: dict,
    search: SearchConfig | None = None,
    sim_workers: int | None = None,
    gpu_price_per_hour: float | None = None,
) -> list[dict]:
    """Tiempo de LLM + simulación, más 300 semillas reservadas y el mismo número en estrés.

    El tiempo de simulación parte de parallel_effective_s medido con los workers del JSON.
    Si sim_workers es distinto, se escala de forma lineal y se deja anotado.
    """
    cfg = search or SearchConfig()
    bench_workers = int(sim_payload["workers"])
    workers = bench_workers if sim_workers is None else sim_workers
    effective = float(sim_payload["parallel_effective_s"])
    if workers != bench_workers and workers > 0:
        effective = effective * bench_workers / workers
    llm_row = _best_llm_row(llm_payload)
    per_min = float(llm_row["valid_per_min"])
    rows = []
    for n in N_VALUES:
        for k in K_VALUES:
            for r in R_VALUES:
                sims = n * k * r + cfg.HOLDOUT_SEEDS + cfg.HOLDOUT_SEEDS
                llm_min = (n * r) / per_min if per_min else float("inf")
                sim_min = sims * effective / 60.0
                total = llm_min + sim_min
                cost = None
                if gpu_price_per_hour is not None:
                    cost = (total / 60.0) * gpu_price_per_hour
                rows.append(
                    {
                        "N": n,
                        "K": k,
                        "R": r,
                        "sims": sims,
                        "llm_min": llm_min,
                        "sim_min": sim_min,
                        "total_min": total,
                        "fits": total <= cfg.SEARCH_TARGET_MIN,
                        "cost_usd": cost,
                        "sim_workers": workers,
                        "llm_concurrency": int(llm_row["concurrency"]),
                    }
                )
    return rows


def recommend(rows: list[dict]) -> dict | None:
    fitting = [row for row in rows if row["fits"]]
    if not fitting:
        return None
    return max(fitting, key=lambda row: (row["sims"], row["N"], row["K"], row["R"]))


def render(rows: list[dict], chosen: dict | None, price: float | None) -> str:
    header = (
        f"{'N':>4} {'K':>5} {'R':>3} {'sims':>8} "
        f"{'llm_min':>8} {'sim_min':>8} {'total':>8} {'cabe':>6}"
    )
    lines = [header]
    for row in rows:
        lines.append(
            f"{row['N']:4d} {row['K']:5d} {row['R']:3d} {row['sims']:8d} "
            f"{row['llm_min']:8.2f} {row['sim_min']:8.2f} {row['total_min']:8.2f} "
            f"{'si' if row['fits'] else 'no':>6}"
        )
    if chosen is None:
        lines.append("recomendación: ninguna combinación cabe en el objetivo")
    else:
        lines.append(
            f"recomendación: N={chosen['N']} K={chosen['K']} R={chosen['R']} "
            f"({chosen['total_min']:.2f} min, {chosen['sims']} sims)"
        )
    if price is None:
        lines.append("costo: GPU_PRICE_PER_HOUR no definida; no se inventa un precio")
    elif chosen is not None and chosen["cost_usd"] is not None:
        lines.append(f"costo estimado de la búsqueda recomendada: ${chosen['cost_usd']:.2f}")
    return "\n".join(lines)


def _price_from_env() -> float | None:
    raw = os.environ.get("GPU_PRICE_PER_HOUR", "").strip()
    if not raw:
        return None
    return float(raw)


def main() -> None:
    sim_path = latest("sim_speed_*.json")
    llm_path = latest("llm_*.json")
    sim_payload = json.loads(sim_path.read_text())
    llm_payload = json.loads(llm_path.read_text())
    workers = int(os.environ["SIM_WORKERS"]) if os.environ.get("SIM_WORKERS") else None
    price = _price_from_env()
    rows = plan(sim_payload, llm_payload, sim_workers=workers, gpu_price_per_hour=price)
    chosen = recommend(rows)
    print(f"sim: {sim_path}")
    print(f"llm: {llm_path}")
    print(render(rows, chosen, price))


if __name__ == "__main__":
    main()
