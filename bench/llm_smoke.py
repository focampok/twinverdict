"""Comprueba que un endpoint OpenAI devuelve políticas válidas con JSON Schema."""

from __future__ import annotations

import argparse
import asyncio
import math

import httpx

from llm.client import LLMClient, ProposeResult


def _percentile(samples: list[float], q: float) -> float:
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[index]


def render_report(model: str, requested: int, result: ProposeResult) -> str:
    valid = len(result.valid)
    invalid = len(result.invalid)
    rate = valid / requested if requested else 0.0
    first_error = result.invalid[0]["error"] if result.invalid else ""
    lines = [
        f"modelo: {model}",
        f"pedidas: {requested}",
        f"válidas: {valid}",
        f"inválidas: {invalid}",
        f"tasa_válidas: {rate:.3f}",
        f"p50_s: {_percentile(result.latencies_s, 0.50):.4f}",
        f"p95_s: {_percentile(result.latencies_s, 0.95):.4f}",
        f"tokens_salida_por_s: {result.tokens_per_s:.2f}",
    ]
    if first_error:
        lines.append(f"primer_error: {first_error}")
    if result.thinking:
        lines.append(
            "aviso: el modelo escribió razonamiento antes del JSON. "
            "Conviene desactivar el thinking o usar un modelo sin él."
        )
    if result.valid:
        example = result.valid[0].model_dump_json(by_alias=True, exclude_none=True)
        lines.append("ejemplo: " + example)
    lines.append("salida_estructurada: response_format json_schema strict")
    return "\n".join(lines)


async def smoke(client: LLMClient, n: int, seed: int, model_name: str) -> tuple[str, int]:
    result = await client.propose("escenario base de la línea M1-M5", n, seed)
    report = render_report(model_name, n, result)
    rate = (len(result.valid) / n) if n else 0.0
    return report, 0 if rate >= 0.95 else 1


async def _reported_model(base_url: str, api_key: str) -> str:
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as http:
        response = await http.get("models", headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        data = response.json().get("data") or []
        if data:
            return str(data[0].get("id") or "desconocido")
    return "desconocido"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke de políticas JSON contra un endpoint OpenAI"
    )
    parser.add_argument("--n", type=int, default=8)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    async def run() -> int:
        client = LLMClient.from_settings()
        try:
            model = await _reported_model(client.base_url, client.api_key)
            report, code = await smoke(client, args.n, args.seed, model)
        finally:
            await client.aclose()
        print(report)
        return code

    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
