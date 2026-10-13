"""Cliente del LLM. Cambiar a vLLM es cambiar LLM_BASE_URL y LLM_MODEL."""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from config import Settings
from llm.prompts import explain_messages, propose_messages
from policy.schema import Policy, parse_policy, policy_json_schema


@dataclass(slots=True)
class ProposeResult:
    valid: list[Policy]
    invalid: list[dict[str, str]]
    latencies_s: list[float]
    completion_tokens: int
    tokens_per_s: float
    wall_s: float
    thinking: bool


def _looks_like_thinking(content: str) -> bool:
    text = content.lstrip()
    if "<think>" in content or "</think>" in content:
        return True
    return text.find("{") > 0


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        concurrency: int = 32,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, http_client=http_client)
        self._limit = asyncio.Semaphore(concurrency)
        self._owns_http = http_client is None

    @classmethod
    def from_settings(cls, concurrency: int = 32) -> LLMClient:
        settings = Settings()
        return cls(
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            concurrency=concurrency,
        )

    async def aclose(self) -> None:
        await self._client.close()

    async def propose(self, context: str, n: int, seed: int) -> ProposeResult:
        schema = policy_json_schema()
        started = time.perf_counter()
        rows = await asyncio.gather(
            *(self._one(context, schema, seed + index) for index in range(n))
        )
        elapsed = max(time.perf_counter() - started, 1e-9)
        valid: list[Policy] = []
        invalid: list[dict[str, str]] = []
        latencies: list[float] = []
        tokens = 0
        thinking = False
        for content, latency, completion_tokens in rows:
            latencies.append(latency)
            tokens += completion_tokens
            thinking = thinking or _looks_like_thinking(content)
            try:
                valid.append(parse_policy(content))
            except Exception as exc:
                invalid.append({"content": content, "error": str(exc)})
        return ProposeResult(
            valid=valid,
            invalid=invalid,
            latencies_s=latencies,
            completion_tokens=tokens,
            tokens_per_s=tokens / elapsed,
            wall_s=elapsed,
            thinking=thinking,
        )

    async def _one(self, context: str, schema: dict, seed: int) -> tuple[str, float, int]:
        async with self._limit:
            started = time.perf_counter()
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=propose_messages(context),
                seed=seed,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "policy", "schema": schema, "strict": True},
                },
                # Qwen3 piensa por defecto; sin esto una petición de la tanda no termina.
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            latency = time.perf_counter() - started
        content = response.choices[0].message.content or ""
        usage = response.usage
        completion = int(usage.completion_tokens) if usage is not None else 0
        return content, latency, completion

    async def explain(self, metrics: dict) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=explain_messages(metrics),
        )
        return response.choices[0].message.content or ""


def _main() -> None:
    parser = argparse.ArgumentParser(description="Pide políticas al endpoint LLM configurado")
    parser.add_argument("--n", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    async def run() -> None:
        client = LLMClient.from_settings()
        try:
            result = await client.propose("escenario base de la línea M1-M5", args.n, args.seed)
        finally:
            await client.aclose()
        print(f"válidas={len(result.valid)} inválidas={len(result.invalid)}")
        for policy in result.valid:
            print(policy.model_dump_json(by_alias=True, exclude_none=True))
        for item in result.invalid:
            print(f"inválida: {item['error']}")

    asyncio.run(run())


if __name__ == "__main__":
    _main()
