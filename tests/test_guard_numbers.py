"""El texto de la tarjeta solo puede citar números de la corrida oficial."""

import json
from pathlib import Path

import pytest

from guard.numbers import UnverifiedNumbers, card_text, extract_numbers, render_card, verify

OFFICIAL_JOB_ID = "c0c92625-de22-4520-accb-6a17c1a76428"
CARD_PATH = (
    Path(__file__).resolve().parents[1]
    / "bench"
    / "results"
    / f"operator_card_{OFFICIAL_JOB_ID}.json"
)


def _card() -> dict:
    return json.loads(CARD_PATH.read_text())


def _visible(rendered: dict[str, str]) -> str:
    return f"{rendered['headline']} {rendered['body']} {rendered['stress_caveat']}"


def test_invented_number_fails() -> None:
    numbers = _card()["numbers"]
    findings = verify("85% a tiempo", numbers)
    assert findings
    assert "85%" in findings[0]
    assert extract_numbers("85% a tiempo") == {"85%"}


def test_text_built_from_official_numbers_passes() -> None:
    card = _card()
    numbers = card["numbers"]
    fixed = numbers["on_time_rate_fixed_holdout"]
    best = numbers["on_time_rate_best_holdout"]
    text = f"{fixed * 100:.1f}% a tiempo frente a {best * 100:.1f}%"
    assert verify(text, numbers) == []

    rendered = render_card(card)
    assert set(rendered) == {"headline", "body", "numbers_used", "stress_caveat"}
    assert verify(_visible(rendered), numbers) == []
    assert rendered["headline"].startswith("On time in holdout:")
    assert "50.6%" in rendered["headline"]
    assert "98.9%" in rendered["headline"]
    assert rendered["body"].startswith("Winning policy:")
    assert "1.369" not in rendered["headline"]
    assert "0.772" not in rendered["headline"]
    assert "CRITICAL_RATIO" in rendered["body"]
    assert rendered["stress_caveat"] in rendered["body"]


def test_one_decimal_percentages_are_accepted() -> None:
    numbers = _card()["numbers"]
    fixed = numbers["on_time_rate_fixed_holdout"]
    best = numbers["on_time_rate_best_holdout"]
    assert f"{fixed * 100:.1f}%" == "50.6%"
    assert f"{best * 100:.1f}%" == "98.9%"
    assert verify("50.6%", numbers) == []
    assert verify("98.9%", numbers) == []
    assert verify("50.5%", numbers)
    assert extract_numbers("50.6% y 98.9%") == {"50.6%", "98.9%"}


def test_replay_ignores_llm_text() -> None:
    card = _card()
    rendered = card_text(card, mode="replay", llm_text="85% a tiempo")
    assert "85%" not in _visible(rendered)
    assert verify(_visible(rendered), card["numbers"]) == []


def test_live_llm_text_must_verify() -> None:
    card = _card()
    with pytest.raises(UnverifiedNumbers) as caught:
        card_text(card, mode="live", llm_text="85% a tiempo")
    assert caught.value.findings

    accepted = card_text(card, mode="live", llm_text="98.9% a tiempo")
    assert accepted["body"] == "98.9% a tiempo"
