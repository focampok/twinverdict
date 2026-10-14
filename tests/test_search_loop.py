import httpx

from llm.client import LLMClient, ProposeResult
from llm.mock_server import app
from policy.schema import Policy, parse_policy
from search.config import SearchConfig
from search.loop import propose_distinct, run_search


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


def _policy(rule: str) -> Policy:
    return parse_policy(
        {
            "version": 1,
            "maintenance": {"pm_wear_threshold": {}, "max_pm_per_shift": 1},
            "dispatch": {"rule": rule},
            "rules": [],
        }
    )


class _Scripted:
    def __init__(self, steps: list[list[Policy | None]]) -> None:
        self.steps = steps
        self.calls: list[tuple[int, int]] = []

    async def propose(self, context: str, n: int, seed: int) -> ProposeResult:
        self.calls.append((n, seed))
        batch = self.steps.pop(0)
        assert len(batch) == n
        return ProposeResult(
            valid=[item for item in batch if item is not None],
            invalid=[{"content": "", "error": "no"} for item in batch if item is None],
            latencies_s=[0.0] * n,
            completion_tokens=n,
            tokens_per_s=1.0,
            wall_s=0.1,
            thinking=False,
        )


async def test_exact_duplicates_are_retried_at_most_twice() -> None:
    same = _policy("SPT")
    fresh = _policy("EDD")
    script = _Scripted([[same, same], [same], [fresh]])
    result, retries = await propose_distinct(script, "prompt", 2, 100)
    assert retries == 2
    assert script.calls == [(2, 100), (1, 102), (1, 103)]
    assert [item.dispatch.rule for item in result.valid] == ["SPT", "EDD"]
    assert script.steps == []


async def test_retries_stop_when_the_copy_remains() -> None:
    same = _policy("SPT")
    script = _Scripted([[same, same], [same], [same]])
    result, retries = await propose_distinct(script, "prompt", 2, 7)
    assert retries == 2
    assert len(script.calls) == 3
    assert [item.dispatch.rule for item in result.valid] == ["SPT", "SPT"]


async def test_unique_round_does_not_retry() -> None:
    script = _Scripted([[_policy("SPT"), _policy("EDD")]])
    result, retries = await propose_distinct(script, "prompt", 2, 4)
    assert retries == 0
    assert script.calls == [(2, 4)]
    assert len(result.valid) == 2
