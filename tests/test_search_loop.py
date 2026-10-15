import httpx

from llm.client import LLMClient, ProposeResult
from llm.mock_server import app
from policy.schema import Policy, fixed_rule_policy, parse_policy
from search.config import SearchConfig
from search.loop import (
    EvaluatedPolicy,
    _rank_key,
    local_and_free_counts,
    propose_distinct,
    run_search,
)
from search.prompts import simulator_key


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
        self.prompts: list[str] = []

    async def propose(self, context: str, n: int, seed: int) -> ProposeResult:
        self.prompts.append(context)
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


async def test_a_clone_is_dropped_when_the_retries_stay_clones() -> None:
    same = _policy("SPT")
    script = _Scripted([[same, same], [same], [same]])
    result, retries = await propose_distinct(script, "prompt", 2, 7)
    assert retries == 2
    assert len(script.calls) == 3
    assert [item.dispatch.rule for item in result.valid] == ["SPT"]


async def test_retry_treats_the_default_threshold_as_the_explicit_one() -> None:
    implicit = _policy("EDD")
    explicit = parse_policy(
        {
            "version": 1,
            "maintenance": {
                "pm_wear_threshold": {"M1": 0.75, "M2": 0.75, "M3": 0.75, "M4": 0.75, "M5": 0.75},
                "max_pm_per_shift": 1,
            },
            "dispatch": {"rule": "EDD"},
            "rules": [],
        }
    )
    fresh = _policy("SPT")
    script = _Scripted([[implicit, explicit], [explicit], [fresh]])
    result, retries = await propose_distinct(script, "prompt", 2, 20)
    assert retries == 2
    assert [item.dispatch.rule for item in result.valid] == ["EDD", "SPT"]


async def test_a_clone_of_a_blocked_policy_is_not_simulated() -> None:
    clone = _policy("EDD")
    fresh = _policy("SPT")
    script = _Scripted([[clone], [clone], [fresh]])
    result, retries = await propose_distinct(script, "prompt", 1, 5, blocked={simulator_key(clone)})
    assert retries == 2
    assert script.calls == [(1, 5), (1, 6), (1, 7)]
    assert [item.dispatch.rule for item in result.valid] == ["SPT"]


def test_default_round_asks_for_24_local_and_24_free() -> None:
    assert local_and_free_counts(48) == (24, 24)
    assert local_and_free_counts(2) == (1, 1)


def test_tie_keeps_the_earlier_round_and_not_a_clone_of_policy_zero() -> None:
    fixed = fixed_rule_policy()
    clone = _policy("EDD")
    assert simulator_key(fixed) == simulator_key(clone)
    earlier = EvaluatedPolicy(
        policy=fixed,
        objective=0.7858,
        kpis={},
        ci_low=0.7858,
        ci_high=0.7858,
        n_seeds=1,
        source="fixed",
        round=0,
    )
    later = EvaluatedPolicy(
        policy=clone,
        objective=0.7858,
        kpis={},
        ci_low=0.7858,
        ci_high=0.7858,
        n_seeds=1,
        source="llm",
        round=1,
    )
    winner = sorted([later, earlier], key=_rank_key)[0]
    assert winner.round == 0
    assert winner.policy is fixed


async def test_round_drops_clones_of_the_fixed_rule_and_asks_both_prompts() -> None:
    clone = _policy("EDD")
    script = _Scripted([[clone] for _ in range(12)])
    config = _short()
    result = await run_search(config, script, "base", 1, workers=1, holdout_seeds=0)  # type: ignore[arg-type]
    assert all(item.valid == [] for item in result.rounds)
    assert result.best_objective == result.fixed_objective
    assert result.policies[0].round == 0
    assert result.simulations_total == config.K
    assert any("cambios locales" in prompt for prompt in script.prompts)
    assert any("política libre" in prompt for prompt in script.prompts)


async def test_unique_round_does_not_retry() -> None:
    script = _Scripted([[_policy("SPT"), _policy("EDD")]])
    result, retries = await propose_distinct(script, "prompt", 2, 4)
    assert retries == 0
    assert script.calls == [(2, 4)]
    assert len(result.valid) == 2
