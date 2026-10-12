from fastapi.testclient import TestClient

from api.main import create_app


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


def test_index_placeholder() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "TwinVerdict" in response.text
    assert "UI en construcción" in response.text
    assert "MODE:" in response.text
