import httpx

from baselines.budget import total_train_sims
from baselines.llm_nofeedback import run_llm_nofeedback
from llm.client import LLMClient
from llm.mock_server import app
from policy.schema import parse_policy
from search.config import SearchConfig
from search.prompts import build_oneshot_prompt


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


def _smoke() -> SearchConfig:
    return SearchConfig.from_profile("smoke")


def test_oneshot_prompt_has_no_candidate_metrics() -> None:
    prompt = build_oneshot_prompt("base")
    assert prompt == build_oneshot_prompt("base")  # fijo entre lotes
    assert "escenario: base" in prompt
    assert '"rule": "EDD"' in prompt  # la regla fija como referencia
    # Sin objetivos, KPIs, top-k ni análisis de fallas de candidatas anteriores.
    assert "kpis" not in prompt
    assert "objetivo=" not in prompt
    assert "politica_1" not in prompt
    assert "paro_no_planificado_h" not in prompt


async def test_smoke_run_respects_budget_and_schema() -> None:
    http, client = _client()
    config = _smoke()
    try:
        result = await run_llm_nofeedback(config, client, "base", 1, workers=1)
    finally:
        await client.aclose()
        await http.aclose()
    assert result.simulations_total <= total_train_sims(config)
    assert result.simulations_total % config.K == 0
    assert result.history[-1]["sims_acumuladas"] == result.simulations_total
    assert result.valid_total <= result.requested
    parse_policy(result.best_policy.model_dump(mode="json", by_alias=True))


async def test_invalid_candidates_do_not_stop_the_run(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_INVALID_RATE", "1")
    http, client = _client()
    config = _smoke()
    try:
        result = await run_llm_nofeedback(config, client, "base", 2, workers=1)
    finally:
        await client.aclose()
        await http.aclose()
    assert result.valid_total == 0
    assert result.invalid_total == result.requested
    assert result.simulations_total == config.K  # solo la regla fija gastó simulaciones
    assert result.best_objective == result.fixed_objective


async def test_same_seed_gives_the_same_best() -> None:
    http, client = _client()
    config = _smoke()
    try:
        first = await run_llm_nofeedback(config, client, "base", 5, workers=1)
        second = await run_llm_nofeedback(config, client, "base", 5, workers=1)
    finally:
        await client.aclose()
        await http.aclose()
    assert first.best_objective == second.best_objective
    assert first.simulations_total == second.simulations_total
