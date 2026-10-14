"""Bucle de búsqueda contra un LLM con interfaz OpenAI. El número lo da el simulador."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from config import Settings
from llm.client import LLMClient, ProposeResult
from policy.schema import Policy, fixed_rule_policy
from search.config import SearchConfig
from search.prompts import build_search_prompt, dedupe_top
from search.repro import build_search_config
from sim.objective import composite_objective, load_objective_weights
from sim.runner import Scenario, simulate_many


@dataclass(slots=True)
class EvaluatedPolicy:
    policy: Policy
    objective: float
    kpis: dict[str, float]
    ci_low: float
    ci_high: float
    n_seeds: int
    source: str
    round: int

    def policy_json(self) -> dict:
        return self.policy.model_dump(mode="json", by_alias=True)


@dataclass(slots=True)
class RoundResult:
    round: int
    prompt: str
    valid: list[Policy]
    invalid: list[dict[str, str]]
    evaluated: list[EvaluatedPolicy]
    latencies_s: list[float]
    sims_spent: int


@dataclass(slots=True)
class SearchResult:
    policies: list[EvaluatedPolicy]
    rounds: list[RoundResult]
    simulations_total: int
    best_policy: Policy
    best_objective: float
    fixed_objective: float
    holdout_objective: float | None
    holdout: EvaluatedPolicy | None
    seed: int
    scenario: str
    train_seeds: list[int]
    holdout_seeds: list[int]
    sim_workers: int
    seconds_per_sim: float
    # Holdout y estrés (+30% fallas, demanda x1.5) de la mejor política y de la regla fija,
    # en las mismas semillas y fuera del presupuesto de entrenamiento. La tarjeta de operador
    # compara las dos políticas, así que las dos tienen que quedar persistidas. Con defaults
    # para que las líneas base puedan construir un SearchResult sin ellas.
    stress: EvaluatedPolicy | None = None
    stress_objective: float | None = None
    fixed_holdout: EvaluatedPolicy | None = None
    fixed_stress: EvaluatedPolicy | None = None


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


def _rank_key(item: EvaluatedPolicy) -> tuple[float, str]:
    body = json.dumps(item.policy_json(), sort_keys=True, ensure_ascii=False)
    return (-item.objective, body)


def _exact_json(policy: Policy) -> str:
    body = policy.model_dump(mode="json", by_alias=True)
    return json.dumps(body, sort_keys=True, ensure_ascii=False)


# Cada duplicado exacto se vuelve a pedir como mucho estas veces. Las semillas de
# reintento caben en el hueco de 10_000 que separa las rondas (N=48 → menos de 200).
MAX_EXACT_RETRIES = 2


class _Proposer(Protocol):
    async def propose(self, context: str, n: int, seed: int) -> ProposeResult: ...


async def propose_distinct(
    llm_client: _Proposer,
    prompt: str,
    n: int,
    seed: int,
    *,
    max_retries: int = MAX_EXACT_RETRIES,
) -> tuple[ProposeResult, int]:
    """Pide n políticas y reintenta las copias exactas, como mucho `max_retries` por copia.

    Se conserva la primera aparición. Cada reintento usa una semilla nueva y, si
    sigue siendo una copia o sale inválido, se agota el cupo y queda la anterior.
    """
    result = await llm_client.propose(prompt, n, seed)
    seen: dict[str, int] = {}
    pending: list[int] = []
    for index, policy in enumerate(result.valid):
        key = _exact_json(policy)
        if key in seen:
            pending.append(index)
        else:
            seen[key] = index
    retries = 0
    next_seed = seed + n
    for _attempt in range(max_retries):
        if not pending:
            break
        seeds = [next_seed + offset for offset in range(len(pending))]
        next_seed += len(pending)
        retries += len(pending)
        refreshed = await asyncio.gather(
            *(llm_client.propose(prompt, 1, retry_seed) for retry_seed in seeds)
        )
        still: list[int] = []
        for index, retry in zip(pending, refreshed, strict=True):
            result.latencies_s.extend(retry.latencies_s)
            result.invalid.extend(retry.invalid)
            result.completion_tokens += retry.completion_tokens
            result.wall_s += retry.wall_s
            result.thinking = result.thinking or retry.thinking
            if not retry.valid:
                still.append(index)
                continue
            candidate = retry.valid[0]
            key = _exact_json(candidate)
            if key in seen:
                still.append(index)
                continue
            seen[key] = index
            result.valid[index] = candidate
        pending = still
    elapsed = max(result.wall_s, 1e-9)
    result.tokens_per_s = result.completion_tokens / elapsed
    return result, retries


def evaluate_policy(
    policy: Policy,
    seeds: list[int],
    workers: int,
    scenario: Scenario,
    source: str,
    round_index: int,
) -> EvaluatedPolicy:
    rows = simulate_many(policy, seeds, workers, scenario=scenario)
    weights = load_objective_weights()
    scores = [composite_objective(row, weights) for row in rows]
    objective, ci_low, ci_high = _confidence(scores)
    return EvaluatedPolicy(
        policy=policy,
        objective=objective,
        kpis=_mean_kpis(rows),
        ci_low=ci_low,
        ci_high=ci_high,
        n_seeds=len(seeds),
        source=source,
        round=round_index,
    )


def _extra_payload(item: EvaluatedPolicy | None) -> dict | None:
    """Resumen de una evaluación fuera del entrenamiento: holdout o estrés."""
    if item is None:
        return None
    return {
        "objective": item.objective,
        "kpis": item.kpis,
        "n_seeds": item.n_seeds,
        "ci_low": item.ci_low,
        "ci_high": item.ci_high,
    }


def result_payload(result: SearchResult, model: str) -> dict:
    def _eval(item: EvaluatedPolicy) -> dict:
        return {
            "policy": item.policy_json(),
            "objective": item.objective,
            "kpis": item.kpis,
            "ci_low": item.ci_low,
            "ci_high": item.ci_high,
            "n_seeds": item.n_seeds,
            "source": item.source,
            "round": item.round,
        }

    return {
        "model": model,
        "seed": result.seed,
        "scenario": result.scenario,
        "simulations_total": result.simulations_total,
        "best_objective": result.best_objective,
        "fixed_objective": result.fixed_objective,
        "holdout_objective": result.holdout_objective,
        "holdout": _extra_payload(result.holdout),
        "stress_objective": result.stress_objective,
        "stress": _extra_payload(result.stress),
        "fixed_holdout": _extra_payload(result.fixed_holdout),
        "fixed_stress": _extra_payload(result.fixed_stress),
        "best_policy": result.best_policy.model_dump(mode="json", by_alias=True),
        "policies": [_eval(item) for item in result.policies],
        "rounds": [
            {
                "round": item.round,
                "prompt": item.prompt,
                "valid": [policy.model_dump(mode="json", by_alias=True) for policy in item.valid],
                "invalid": item.invalid,
                "latencies_s": item.latencies_s,
                "sims_spent": item.sims_spent,
                "evaluated": [_eval(scored) for scored in item.evaluated],
            }
            for item in result.rounds
        ],
    }


async def run_search(
    config: SearchConfig,
    llm_client: LLMClient,
    scenario: Scenario,
    rng_seed: int,
    workers: int | None = None,
    holdout_seeds: int = 0,
) -> SearchResult:
    """política_0 es la regla fija. Cada ronda propone N, simula las válidas en K semillas."""
    pool_workers = Settings().SIM_WORKERS if workers is None else workers
    train_seeds = list(range(rng_seed, rng_seed + config.K))
    sim_seconds = 0.0

    def _timed(
        policy: Policy,
        seeds: list[int],
        source: str,
        round_index: int,
        stressed: bool = False,
    ) -> EvaluatedPolicy:
        nonlocal sim_seconds
        started = time.perf_counter()
        named = "stress" if stressed else scenario
        scored = evaluate_policy(policy, seeds, pool_workers, named, source, round_index)
        sim_seconds += time.perf_counter() - started
        return scored

    fixed = _timed(fixed_rule_policy(), train_seeds, "fixed", 0)
    pool = [fixed]
    policies = [fixed]
    rounds: list[RoundResult] = []
    sims = config.K
    for round_index in range(1, config.R + 1):
        top = dedupe_top(sorted(pool, key=_rank_key), config.TOP_K)
        prompt = build_search_prompt(scenario, top)
        proposed, retries = await propose_distinct(
            llm_client, prompt, config.N, rng_seed + round_index * 10_000
        )
        evaluated: list[EvaluatedPolicy] = []
        for policy in proposed.valid:
            evaluated.append(_timed(policy, train_seeds, "llm", round_index))
        sims += len(evaluated) * config.K
        pool.extend(evaluated)
        policies.extend(evaluated)
        rounds.append(
            RoundResult(
                round=round_index,
                prompt=prompt,
                valid=list(proposed.valid),
                invalid=list(proposed.invalid),
                evaluated=evaluated,
                latencies_s=list(proposed.latencies_s),
                sims_spent=len(evaluated) * config.K,
            )
        )
        best_now = sorted(pool, key=_rank_key)[0]
        print(
            f"ronda {round_index}/{config.R} validas={len(proposed.valid)} "
            f"invalidas={len(proposed.invalid)} reintentos={retries} "
            f"sims={sims} mejor={best_now.objective:.4f}",
            flush=True,
        )
    best = sorted(pool, key=_rank_key)[0]
    holdout = None
    stress = None
    fixed_holdout = None
    fixed_stress = None
    hold_seeds: list[int] = []
    if holdout_seeds > 0:
        hold_seeds = list(range(1_000_000 + rng_seed, 1_000_000 + rng_seed + holdout_seeds))
        holdout = _timed(best.policy, hold_seeds, best.source, -1)
        stress = _timed(best.policy, hold_seeds, best.source, -2, stressed=True)
        fixed_holdout = _timed(fixed.policy, hold_seeds, "fixed", -1)
        fixed_stress = _timed(fixed.policy, hold_seeds, "fixed", -2, stressed=True)
        # Las cuatro evaluaciones quedan fuera del presupuesto de entrenamiento y se suman a
        # simulations_total, igual que el holdout de siempre (misma convención).
        sims += holdout_seeds * 4
    return SearchResult(
        policies=policies,
        rounds=rounds,
        simulations_total=sims,
        best_policy=best.policy,
        best_objective=best.objective,
        fixed_objective=fixed.objective,
        holdout_objective=None if holdout is None else holdout.objective,
        holdout=holdout,
        seed=rng_seed,
        scenario=scenario,
        train_seeds=train_seeds,
        holdout_seeds=hold_seeds,
        sim_workers=pool_workers,
        seconds_per_sim=sim_seconds / sims if sims else 0.0,
        stress=stress,
        stress_objective=None if stress is None else stress.objective,
        fixed_holdout=fixed_holdout,
        fixed_stress=fixed_stress,
    )


def _config_from_args(args: argparse.Namespace) -> SearchConfig:
    updates = {}
    if args.n is not None:
        updates["N"] = args.n
    if args.k is not None:
        updates["K"] = args.k
    if args.r is not None:
        updates["R"] = args.r
    config = SearchConfig()
    if updates:
        return config.model_copy(update=updates)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Búsqueda de políticas contra el LLM configurado")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scenario", default="base", choices=("base", "stress"))
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--k", type=int, default=None)
    parser.add_argument("--r", type=int, default=None)
    parser.add_argument("--holdout", type=int, default=30)
    args = parser.parse_args()
    config = _config_from_args(args)

    async def run() -> SearchResult:
        client = LLMClient.from_settings(concurrency=config.N)
        try:
            return await run_search(
                config,
                client,
                args.scenario,
                args.seed,
                holdout_seeds=args.holdout,
            )
        finally:
            await client.aclose()

    result = asyncio.run(run())
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    path = Path("bench/results") / f"search_mock_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result_payload(result, Settings().LLM_MODEL)
    # El JSON lleva su propio bloque de configuración: N/K/R, perfil, commit y de dónde
    # salieron las políticas. Así la curva de eficiencia lo compara sin banderas a mano.
    payload["config"] = build_search_config(config, result, Settings().LLM_MODEL)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"mejor={result.best_objective:.4f} fija={result.fixed_objective:.4f} "
        f"sims={result.simulations_total} json={path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
