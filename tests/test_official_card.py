"""La tarjeta oficial de la demo se lee del JSON versionado, sin base de datos."""

import json
from pathlib import Path

import pytest

OFFICIAL_JOB_ID = "c0c92625-de22-4520-accb-6a17c1a76428"
CARD_PATH = (
    Path(__file__).resolve().parents[1]
    / "bench"
    / "results"
    / f"operator_card_{OFFICIAL_JOB_ID}.json"
)


def test_official_operator_card_holdout_on_time() -> None:
    card = json.loads(CARD_PATH.read_text())
    numbers = card["numbers"]
    assert card["job_id"] == OFFICIAL_JOB_ID
    assert numbers["on_time_rate_fixed_holdout"] == pytest.approx(0.506, abs=1e-3)
    assert numbers["on_time_rate_best_holdout"] == pytest.approx(0.989, abs=1e-3)
