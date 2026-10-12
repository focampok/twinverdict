import os

import httpx
import pytest

from llm.client import LLMClient
from llm.mock_server import app


def _client() -> tuple[httpx.AsyncClient, LLMClient]:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    client = LLMClient(
        base_url="http://test/v1",
        model="mock",
        api_key="mock",
        concurrency=8,
        http_client=http,
    )
    return http, client


@pytest.fixture(autouse=True)
def _clear_invalid_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOCK_INVALID_RATE", raising=False)


async def test_propose_returns_valid_policies_and_latency() -> None:
    http, client = _client()
    try:
        result = await client.propose("escenario base", n=8, seed=11)
    finally:
        await client.aclose()
        await http.aclose()
    assert len(result.valid) == 8
    assert result.invalid == []
    assert len(result.latencies_s) == 8
    assert all(latency >= 0 for latency in result.latencies_s)
    assert result.tokens_per_s > 0


async def test_invalid_rate_keeps_going(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_INVALID_RATE", "0.5")
    assert os.environ["MOCK_INVALID_RATE"] == "0.5"
    http, client = _client()
    try:
        result = await client.propose("escenario base", n=20, seed=3)
    finally:
        await client.aclose()
        await http.aclose()
    assert result.invalid
    assert len(result.valid) + len(result.invalid) == 20
    assert result.valid


async def test_same_seed_same_policies() -> None:
    http, client = _client()
    try:
        first = await client.propose("escenario base", n=4, seed=9)
        second = await client.propose("escenario base", n=4, seed=9)
    finally:
        await client.aclose()
        await http.aclose()
    first_dump = [policy.model_dump(by_alias=True) for policy in first.valid]
    second_dump = [policy.model_dump(by_alias=True) for policy in second.valid]
    assert first_dump == second_dump
    assert len(first_dump) == 4
