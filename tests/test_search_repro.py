import pytest

from policy.schema import fixed_rule_policy
from search.config import SearchConfig
from search.loop import SearchResult
from search.repro import build_search_config, llm_source

MOCK_URL = "http://127.0.0.1:8001/v1"
# vLLM se usa por túnel SSH: también es loopback, así que el host no lo distingue del mock.
TUNNEL_URL = "http://127.0.0.1:8000/v1"


@pytest.mark.parametrize(
    ("base_url", "model", "expected"),
    [
        (MOCK_URL, "Qwen/Qwen3-8B", "mock"),
        ("http://localhost:8001/v1", "Qwen/Qwen3-8B", "mock"),
        (TUNNEL_URL, "Qwen/Qwen3-8B", "vllm"),
        ("https://vllm.example.com/v1", "Qwen/Qwen3-8B", "vllm"),
        (MOCK_URL, "none", "none"),  # Optuna no pasa por el LLM
    ],
)
def test_llm_source(base_url: str, model: str, expected: str) -> None:
    assert llm_source(base_url, model) == expected


def test_llm_source_follows_a_redefined_mock_port(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_LLM_PORT", "9000")
    assert llm_source("http://127.0.0.1:9000/v1", "Qwen/Qwen3-8B") == "mock"
    assert llm_source(MOCK_URL, "Qwen/Qwen3-8B") == "vllm"


def test_build_search_config_records_the_endpoint_and_the_source() -> None:
    result = SearchResult(
        policies=[],
        rounds=[],
        simulations_total=10,
        best_policy=fixed_rule_policy(),
        best_objective=0.5,
        fixed_objective=0.2,
        holdout_objective=None,
        holdout=None,
        seed=1,
        scenario="base",
        train_seeds=[1, 2],
        holdout_seeds=[],
        sim_workers=1,
        seconds_per_sim=0.01,
    )
    config = SearchConfig.from_profile("smoke")
    payload = build_search_config(config, result, "Qwen/Qwen3-8B", llm_base_url=MOCK_URL)
    assert payload["llm_base_url"] == MOCK_URL
    assert payload["llm_source"] == "mock"
    assert payload["K"] == config.K
    assert payload["failure_midpoint"] == 0.95
    assert payload["failure_steepness"] == 18.0
