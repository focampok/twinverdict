"""Línea base del LLM sin retroalimentación: mide cuánto aporta el bucle.

El LLM propone N*R políticas con un solo prompt fijo y no ve lo que midió la ronda
anterior: ni objetivos, ni KPIs, ni el top-k. Mismo presupuesto de simulaciones que
una búsqueda del perfil, mismas semillas de entrenamiento y el mismo escenario.

Las semillas de muestreo son las del bucle (rng_seed + lote*10_000), para que la
única variable entre esta línea base y el bucle sea el texto del prompt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from baselines.budget import total_train_sims, train_seeds
from config import Settings
from llm.client import LLMClient
from policy.schema import Policy, fixed_rule_policy
from search.config import SearchConfig
from search.loop import EvaluatedPolicy, SearchResult, evaluate_policy
from search.prompts import build_oneshot_prompt
from search.repro import build_search_config
from sim.runner import Scenario


@dataclass(slots=True)
class NoFeedbackResult:
    best_policy: Policy
    best_objective: float
    fixed_objective: float
    simulations_total: int
    history: list[dict[str, float | int]]
    requested: int
    valid_total: int
    invalid_total: int
    sim_workers: int
    seconds_per_sim: float
    train_seeds: list[int]
    seed: int
    scenario: Scenario


async def run_llm_nofeedback(
    config: SearchConfig,
    llm_client: LLMClient,
    scenario: Scenario,
    rng_seed: int,
    workers: int | None = None,
) -> NoFeedbackResult:
    """La política 0 es la regla fija. R lotes de N propuestas con el mismo prompt."""
    pool_workers = Settings().SIM_WORKERS if workers is None else workers
    seeds = train_seeds(config, rng_seed)
    prompt = build_oneshot_prompt(scenario)
    sim_seconds = 0.0

    def _timed(policy: Policy, source: str, batch: int) -> EvaluatedPolicy:
        nonlocal sim_seconds
        started = time.perf_counter()
        scored = evaluate_policy(policy, seeds, pool_workers, scenario, source, batch)
        sim_seconds += time.perf_counter() - started
        return scored

    fixed = _timed(fixed_rule_policy(), "fixed", 0)
    best = fixed
    sims = config.K
    valid_total = 0
    invalid_total = 0
    history: list[dict[str, float | int]] = [
        {"batch": 0, "sims_acumuladas": sims, "best_so_far": best.objective}
    ]
    for batch in range(1, config.R + 1):
        proposed = await llm_client.propose(prompt, config.N, rng_seed + batch * 10_000)
        valid_total += len(proposed.valid)
        invalid_total += len(proposed.invalid)
        for policy in proposed.valid:
            scored = _timed(policy, "llm_nofeedback", batch)
            sims += config.K
            if scored.objective > best.objective:
                best = scored
        history.append({"batch": batch, "sims_acumuladas": sims, "best_so_far": best.objective})
        print(
            f"lote {batch}/{config.R} validas={len(proposed.valid)} "
            f"invalidas={len(proposed.invalid)} sims={sims} mejor={best.objective:.4f}",
            flush=True,
        )
    return NoFeedbackResult(
        best_policy=best.policy,
        best_objective=best.objective,
        fixed_objective=fixed.objective,
        simulations_total=sims,
        history=history,
        requested=config.N * config.R,
        valid_total=valid_total,
        invalid_total=invalid_total,
        sim_workers=pool_workers,
        seconds_per_sim=sim_seconds / sims if sims else 0.0,
        train_seeds=seeds,
        seed=rng_seed,
        scenario=scenario,
    )


def result_payload(config: SearchConfig, result: NoFeedbackResult, model: str) -> dict:
    """Mismo formato y metadatos que el Prompt 15, con el modelo que propuso."""
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
        "method": "llm_nofeedback",
        "best_policy": result.best_policy.model_dump(mode="json", by_alias=True),
        "best_objective": result.best_objective,
        "fixed_objective": result.fixed_objective,
        "simulations_total": result.simulations_total,
        "requested": result.requested,
        "valid": result.valid_total,
        "invalid": result.invalid_total,
        "history": result.history,
        "config": build_search_config(config, as_search, model),
    }


def write_result(
    config: SearchConfig, result: NoFeedbackResult, model: str, directory: Path
) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    path = directory / f"llm_nofeedback_{config.profile}_seed{result.seed}_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_payload(config, result, model), indent=2) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Línea base del LLM sin retroalimentación, presupuesto igual"
    )
    parser.add_argument("--profile", default="default")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scenario", default="base", choices=("base", "stress"))
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("bench/results"))
    args = parser.parse_args()

    config = SearchConfig.from_profile(args.profile)

    async def run() -> NoFeedbackResult:
        client = LLMClient.from_settings(concurrency=config.N)
        try:
            return await run_llm_nofeedback(
                config, client, args.scenario, args.seed, workers=args.workers
            )
        finally:
            await client.aclose()

    started = time.perf_counter()
    result = asyncio.run(run())
    path = write_result(config, result, Settings().LLM_MODEL, args.out)
    minutes = (time.perf_counter() - started) / 60.0
    print(
        f"llm sin retroalimentacion {args.profile} seed={args.seed}: "
        f"mejor={result.best_objective:.4f} fija={result.fixed_objective:.4f} "
        f"sims={result.simulations_total}/{total_train_sims(config)} "
        f"validas={result.valid_total}/{result.requested} {minutes:.1f} min json={path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
