"""Políticas válidas por minuto contra un endpoint compatible con OpenAI."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import httpx

from llm.client import LLMClient


def _percentile(samples: list[float], q: float) -> float:
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[index]


async def measure(concurrency: int, n: int, seed: int) -> dict[str, float | int]:
    client = LLMClient.from_settings(concurrency=concurrency)
    try:
        result = await client.propose("escenario base de la línea M1-M5", n, seed)
    finally:
        await client.aclose()
    valid = len(result.valid)
    per_min = (valid / result.wall_s) * 60.0 if result.wall_s else 0.0
    return {
        "concurrency": concurrency,
        "valid_per_min": per_min,
        "tokens_per_s": result.tokens_per_s,
        "p50_s": _percentile(result.latencies_s, 0.50),
        "p95_s": _percentile(result.latencies_s, 0.95),
        "valid_rate": valid / n if n else 0.0,
        "n": n,
        "valid": valid,
    }


def render_table(rows: list[dict]) -> str:
    header = f"{'conc':>6} {'validas/min':>12} {'tok/s':>10} {'p50_s':>8} {'p95_s':>8} {'tasa':>8}"
    lines = [header]
    for row in rows:
        lines.append(
            f"{int(row['concurrency']):6d} {float(row['valid_per_min']):12.1f} "
            f"{float(row['tokens_per_s']):10.1f} {float(row['p50_s']):8.4f} "
            f"{float(row['p95_s']):8.4f} {float(row['valid_rate']):8.3f}"
        )
    return "\n".join(lines)


def write_result(model: str, rows: list[dict]) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    safe = model.replace("/", "_")
    path = Path("bench/results") / f"llm_{safe}_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "created": stamp, "rows": rows}
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


async def reported_model() -> str:
    client = LLMClient.from_settings()
    try:
        async with httpx.AsyncClient(base_url=client.base_url, timeout=10) as http:
            response = await http.get(
                "models",
                headers={"Authorization": f"Bearer {client.api_key}"},
            )
            response.raise_for_status()
            data = response.json().get("data") or []
            if data:
                return str(data[0].get("id") or client.model)
            return client.model
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Throughput del endpoint de políticas")
    parser.add_argument("--concurrency", default="8,16,32,64")
    parser.add_argument("--n", type=int, default=64)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    levels = [int(part) for part in args.concurrency.split(",") if part]

    async def run() -> None:
        model = await reported_model()
        rows = [await measure(level, args.n, args.seed + level) for level in levels]
        print(render_table(rows))
        path = write_result(model, rows)
        print(f"json: {path}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
