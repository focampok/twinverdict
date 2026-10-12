import httpx

from bench.llm_smoke import smoke
from llm.client import LLMClient
from llm.mock_server import app


async def test_smoke_against_mock_reports_valid_policies() -> None:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    client = LLMClient(
        base_url="http://test/v1",
        model="mock",
        api_key="mock",
        concurrency=8,
        http_client=http,
    )
    try:
        report, code = await smoke(client, n=8, seed=2, model_name="mock")
    finally:
        await client.aclose()
        await http.aclose()
    assert code == 0
    assert "modelo: mock" in report
    assert "pedidas: 8" in report
    assert "válidas: 8" in report
    assert "inválidas: 0" in report
    assert "p50_s:" in report
    assert "p95_s:" in report
    assert "tokens_salida_por_s:" in report
    assert "ejemplo:" in report
    assert "response_format json_schema strict" in report
