import httpx

from llm.client import LLMClient
from llm.mock_server import app
from policy.schema import parse_policy
from search.config import SearchConfig
from search.loop import run_search


def _client() -> tuple[httpx.AsyncClient, LLMClient]:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    client = LLMClient(
        base_url="http://test/v1",
        model="mock",
        api_key="mock",
        concurrency=4,
        http_client=http,
    )
    return http, client


def _short() -> SearchConfig:
    return SearchConfig.from_profile("smoke")


async def test_short_search_is_schema_valid_and_deterministic() -> None:
    http, client = _client()
    config = _short()
    try:
        first = await run_search(config, client, "base", 1, workers=1, holdout_seeds=0)
        second = await run_search(config, client, "base", 1, workers=1, holdout_seeds=0)
    finally:
        await client.aclose()
        await http.aclose()
    assert first.best_objective == second.best_objective
    assert first.simulations_total == second.simulations_total
    expected = config.K
    for item in first.rounds:
        expected += len(item.valid) * config.K
        for policy in item.valid:
            parse_policy(policy.model_dump(mode="json", by_alias=True))
    assert first.simulations_total == expected
    assert first.policies
    assert first.fixed_objective == first.policies[0].objective


async def test_invalid_candidates_do_not_stop_the_loop(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_INVALID_RATE", "1")
    http, client = _client()
    config = _short()
    try:
        result = await run_search(config, client, "base", 3, workers=1, holdout_seeds=0)
    finally:
        await client.aclose()
        await http.aclose()
    assert result.rounds
    assert all(item.valid == [] for item in result.rounds)
    assert all(item.invalid for item in result.rounds)
    assert result.simulations_total == config.K
    assert result.best_objective == result.fixed_objective
