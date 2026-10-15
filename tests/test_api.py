import uuid

from fastapi.testclient import TestClient

from api.main import create_app

OFFICIAL_JOB_ID = "285d1787-5d7c-464a-9897-4c585663f088"
WINNING_POLICY_ID = "9632bd63-c0cd-4f7a-bf48-ddbd77970760"


def test_healthz() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_without_database() -> None:
    url = "postgresql+psycopg://planta:planta@127.0.0.1:1/nope"
    with TestClient(create_app(url)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503


def test_replay_index_shows_the_operator_card(monkeypatch) -> None:
    monkeypatch.setenv("MODE", "replay")
    monkeypatch.setenv("REPLAY_JOB_ID", OFFICIAL_JOB_ID)
    with TestClient(create_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "REPLAY" in response.text
    assert "%" in response.text
    assert "vLLM real (Qwen3-8B), planta calibrada" in response.text
    assert "A tiempo en holdout" in response.text
    assert "Intervalo del objetivo" in response.text
    assert "Política ganadora" in response.text
    assert "estrés" in response.text
    assert "El texto no se muestra" not in response.text


def test_verify_failure_hides_the_card_text(monkeypatch) -> None:
    monkeypatch.setenv("MODE", "replay")
    monkeypatch.setenv("REPLAY_JOB_ID", OFFICIAL_JOB_ID)
    monkeypatch.setattr(
        "api.operator.verify",
        lambda text, numbers, **kwargs: ["número fuera de la tarjeta: 85%"],
    )
    with TestClient(create_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "El texto no se muestra" in response.text
    assert "A tiempo en holdout" not in response.text
    assert "Política ganadora" not in response.text


def test_efficiency_endpoint_and_chart_canvas() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/efficiency")
        page = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert {
        "date",
        "profile",
        "seed",
        "scenario",
        "llm_source",
        "k",
        "target",
        "best_global",
        "fixed",
        "methods",
    } <= set(payload)
    assert payload["date"] == "20261015"
    assert [item["name"] for item in payload["methods"]] == [
        "regla fija",
        "Optuna TPE",
        "LLM sin retroalimentación",
        "bucle con retroalimentación",
    ]
    assert '<canvas id="efficiency-chart"' in page.text
    assert "Eficiencia" in page.text
    assert "umbral 90%" in page.text
    assert "dataset público" in page.text
    assert "—" in page.text


def test_replay_serves_the_card_without_postgres_and_blocks_jobs(monkeypatch) -> None:
    monkeypatch.setenv("MODE", "replay")
    monkeypatch.setenv("REPLAY_JOB_ID", OFFICIAL_JOB_ID)
    url = "postgresql+psycopg://planta:planta@127.0.0.1:1/nope"
    with TestClient(create_app(url)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "REPLAY" in page.text
        assert "A tiempo en holdout" in page.text
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/efficiency").status_code == 200
        blocked = client.post("/jobs")
    assert blocked.status_code == 503
    assert blocked.json() == {"error": "replay_only"}


def test_replay_json_comes_from_disk() -> None:
    with TestClient(create_app()) as client:
        response = client.get(f"/api/replay/{OFFICIAL_JOB_ID}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["id"] == OFFICIAL_JOB_ID
    assert payload["run"]["best_policy_id"] == WINNING_POLICY_ID


def test_approve_requires_admin_token_and_persists(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "sekret")
    monkeypatch.setenv("MODE", "replay")
    monkeypatch.setenv("REPLAY_JOB_ID", OFFICIAL_JOB_ID)
    url = "postgresql+psycopg://planta:planta@127.0.0.1:1/nope"
    with TestClient(create_app(url)) as client:
        missing = client.post(f"/policies/{WINNING_POLICY_ID}/approve")
        assert missing.status_code == 401
        wrong = client.post(
            f"/policies/{WINNING_POLICY_ID}/approve",
            headers={"ADMIN_TOKEN": "no"},
        )
        assert wrong.status_code == 401
        ok = client.post(
            f"/policies/{WINNING_POLICY_ID}/approve",
            headers={"ADMIN_TOKEN": "sekret"},
            json={"reason": "lista para el turno"},
        )
        assert ok.status_code == 200
        assert "Aprobada" in ok.text
        assert "lista para el turno" in ok.text
        page = client.get("/")
        assert "Aprobada" in page.text


def test_reject_with_token(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "sekret")
    with TestClient(create_app()) as client:
        response = client.post(
            f"/policies/{uuid.uuid4()}/reject",
            headers={"ADMIN_TOKEN": "sekret"},
        )
    assert response.status_code == 200
    assert "Rechazada" in response.text
