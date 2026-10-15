"""La tarjeta oficial de la demo se lee del JSON versionado, sin base de datos."""

import json
from pathlib import Path

import pytest

OFFICIAL_JOB_ID = "285d1787-5d7c-464a-9897-4c585663f088"
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
    assert numbers["on_time_rate_best_holdout"] == pytest.approx(0.988, abs=1e-3)
