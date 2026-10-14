import os

import httpx
import pytest

from config import Settings
from llm.client import LLMClient
from llm.mock_server import app
from policy.schema import fixed_rule_policy


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


async def test_sampling_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    monkeypatch.delenv("LLM_TOP_P", raising=False)
    monkeypatch.delenv("LLM_TOP_K", raising=False)
    defaults = Settings()
    assert defaults.LLM_TEMPERATURE == 1.0
    assert defaults.LLM_TOP_P == 0.95
    assert defaults.LLM_TOP_K == -1

    monkeypatch.setenv("LLM_TEMPERATURE", "0.4")
    monkeypatch.setenv("LLM_TOP_P", "0.8")
    monkeypatch.setenv("LLM_TOP_K", "50")
    overridden = Settings()
    assert overridden.LLM_TEMPERATURE == 0.4
    assert overridden.LLM_TOP_P == 0.8
    assert overridden.LLM_TOP_K == 50
    client = LLMClient.from_settings()
    try:
        assert (client.temperature, client.top_p, client.top_k) == (0.4, 0.8, 50)
    finally:
        await client.aclose()


async def test_propose_sends_temperature_top_p_and_open_top_k() -> None:
    captured: list[dict] = []

    class _Completions:
        async def create(self, **kwargs: object) -> object:
            captured.append(kwargs)
            content = fixed_rule_policy().model_dump_json(by_alias=True)

            class _Message:
                def __init__(self) -> None:
                    self.content = content

            class _Choice:
                def __init__(self) -> None:
                    self.message = _Message()

            class _Usage:
                completion_tokens = 12

            class _Response:
                choices = [_Choice()]
                usage = _Usage()

            return _Response()

    class _Chat:
        completions = _Completions()

    class _Stub:
        chat = _Chat()

        async def close(self) -> None:
            return None

    client = LLMClient(
        base_url="http://test/v1",
        model="mock",
        api_key="mock",
        temperature=1.0,
        top_p=0.95,
        top_k=-1,
    )
    original = client._client
    client._client = _Stub()  # type: ignore[assignment]
    try:
        result = await client.propose("escenario base", n=1, seed=7)
    finally:
        await client.aclose()
        await original.close()
    assert len(result.valid) == 1
    assert len(captured) == 1
    body = captured[0]
    assert body["temperature"] == 1.0
    assert body["top_p"] == 0.95
    assert body["seed"] == 7
    assert body["extra_body"] == {
        "top_k": -1,
        "chat_template_kwargs": {"enable_thinking": False},
    }
