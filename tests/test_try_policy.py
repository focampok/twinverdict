import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.try_policy import RateLimiter, controls, reference_policies, summarize
from policy.schema import MACHINES, fixed_rule_policy
from sim.calibration import calibrated_plant_config
from sim.runner import simulate_many

OFFICIAL_JOB_ID = "c0c92625-de22-4520-accb-6a17c1a76428"


@pytest.fixture(autouse=True)
def _replay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODE", "replay")
    monkeypatch.setenv("REPLAY_JOB_ID", OFFICIAL_JOB_ID)


def _fixed_json() -> dict:
    return fixed_rule_policy().model_dump(by_alias=True, mode="json")


def _form(preset: dict) -> dict[str, str]:
    fields = {"rule": preset["rule"], "max_pm_per_shift": str(preset["max_pm_per_shift"])}
    fields |= {f"w_{key}": str(value) for key, value in preset["weights"].items()}
    fields |= {f"pm_{machine}": str(preset["thresholds"][machine]) for machine in MACHINES}
    fields["rules"] = json.dumps(preset["rules"])
    return fields


def _rows(payload: dict) -> dict[str, dict]:
    return {row["key"]: row for row in payload["rows"]}


def test_invalid_schema_is_422() -> None:
    bad = _fixed_json()
    bad["maintenance"]["pm_wear_threshold"]["M1"] = 0.2
    with TestClient(create_app()) as client:
        response = client.post("/api/try-policy", json=bad)
        unknown = client.post("/api/try-policy", json={**_fixed_json(), "code": "import os"})
    assert response.status_code == 422
    assert "pm_wear_threshold" in response.json()["detail"]
    assert unknown.status_code == 422
    assert "code" in unknown.json()["detail"]


def test_fixed_rule_reproduces_its_kpis() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/try-policy", json=_fixed_json())
    assert response.status_code == 200
    payload = response.json()
    rows = _rows(payload)
    fixed, _, seeds, official = reference_policies(OFFICIAL_JOB_ID)
    expected = summarize(simulate_many(fixed, seeds, 1, calibrated_plant_config()))
    assert payload["seeds"] == list(range(1_000_001, 1_000_021))
    assert official == 300
    for key, value in expected.items():
        assert rows["user"][key] == value
        assert rows["fixed"][key] == value
    assert payload["gantt"]["proposed"] == payload["gantt"]["baseline"]


def test_llm_preset_through_the_form_reproduces_the_llm_row() -> None:
    _, llm, _, _ = reference_policies(OFFICIAL_JOB_ID)
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/try-policy", data=_form(controls(llm)), headers={"HX-Request": "true"}
        )
        json_response = client.post("/api/try-policy", data=_form(controls(llm)))
    assert response.status_code == 200
    assert "20 holdout seeds; official card uses 300." in response.text
    assert "try-gantt-data" in response.text
    rows = _rows(json_response.json())
    for key in ("on_time_rate", "unplanned_min", "objective", "objective_ci_low"):
        assert rows["user"][key] == rows["llm"][key]


def test_response_is_deterministic() -> None:
    policy = _fixed_json()
    policy["dispatch"] = {"rule": "SPT"}
    policy["maintenance"]["pm_wear_threshold"]["M3"] = 0.6
    with TestClient(create_app()) as client:
        first = client.post("/api/try-policy", json=policy)
        second = client.post("/api/try-policy", json=policy)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_timeout_is_504() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.try_timeout_s = 0.0
        response = client.post("/api/try-policy", json=_fixed_json())
    assert response.status_code == 504


def test_rate_limit_is_429() -> None:
    with TestClient(create_app()) as client:
        statuses = [
            client.post("/api/try-policy", json={"bad": True}).status_code for _ in range(7)
        ]
        other_ip = client.post(
            "/api/try-policy", json={"bad": True}, headers={"X-Forwarded-For": "203.0.113.9"}
        )
    assert statuses == [422] * 6 + [429]
    assert other_ip.status_code == 422


def test_rate_limiter_window_slides() -> None:
    limiter = RateLimiter(limit=2, window_s=60.0)
    assert limiter.allow("a", 0.0)
    assert limiter.allow("a", 1.0)
    assert not limiter.allow("a", 59.0)
    assert limiter.allow("a", 60.0)


def test_endpoint_does_not_import_an_llm_client() -> None:
    script = (
        "import os, sys\n"
        "os.environ['MODE'] = 'replay'\n"
        "from fastapi.testclient import TestClient\n"
        "from api.main import create_app\n"
        "from policy.schema import fixed_rule_policy\n"
        "with TestClient(create_app()) as client:\n"
        "    policy = fixed_rule_policy().model_dump(by_alias=True, mode='json')\n"
        "    assert client.post('/api/try-policy', json=policy).status_code == 200\n"
        "loaded = [name for name in sys.modules if name == 'openai' or name.startswith('openai.')"
        " or name == 'llm' or name.startswith('llm.') or name.startswith('worker')]\n"
        "assert not loaded, loaded\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr


def test_index_shows_the_try_a_policy_panel() -> None:
    with TestClient(create_app()) as client:
        page = client.get("/")
        core = client.get("/visual/gantt-core.js")
    assert page.status_code == 200
    for text in ("Try a policy", "Load fixed rule", "Load LLM best policy", "Simulate"):
        assert text in page.text
    assert core.status_code == 200
    assert "TwinGantt" in core.text
