"""Texto de la tarjeta. Cada cifra sale de operator_card['numbers'] y pasa por verify."""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from config import Settings

# Un % pegado al número cuenta como un solo literal ("50.6%"), no como "50.6".
_LITERAL = re.compile(r"(?<![\d.])(-?\d+(?:\.\d+)?%?)")

Mode = Literal["live", "replay"]


class UnverifiedNumbers(ValueError):
    """El texto trae una cifra que no está en el mapa medido."""

    def __init__(self, findings: list[str]) -> None:
        self.findings = findings
        super().__init__("; ".join(findings))


def extract_numbers(text: str) -> set[str]:
    """Literales numéricos del texto: enteros, decimales y porcentajes."""
    return set(_LITERAL.findall(text))


def verify(text: str, numbers: dict[str, float], *, rtol: float = 1e-4) -> list[str]:
    """Hallazgos: cada literal tiene que coincidir con algún valor medido.

    Un porcentaje se compara contra valor×100 y se acepta el redondeo a 1 decimal.
    El resto se compara con tolerancia relativa `rtol`.
    """
    values = [float(value) for value in numbers.values()]
    findings: list[str] = []
    seen: set[str] = set()
    for literal in _LITERAL.findall(text):
        if literal in seen:
            continue
        seen.add(literal)
        if not _matches(literal, values, rtol):
            findings.append(f"número fuera de la tarjeta: {literal}")
    return findings


def render_card(card: dict[str, Any]) -> dict[str, Any]:
    """Titular de % a tiempo en holdout, política ganadora y nota de estrés.

    No usa el objetivo compuesto ni llama al LLM.
    """
    numbers = {key: float(value) for key, value in card["numbers"].items()}
    fixed = _percent(numbers["on_time_rate_fixed_holdout"])
    best = _percent(numbers["on_time_rate_best_holdout"])
    headline = f"A tiempo en holdout: {fixed} con la regla fija, {best} con la mejor política."
    policy = card.get("winning_policy") or {}
    rule = str(policy.get("dispatch_rule") or "sin regla")
    pm = _plain(numbers["best_max_pm_per_shift"])
    rules = _plain(numbers["best_rules"])
    stress_caveat = _stress_caveat(numbers)
    body = (
        f"Política ganadora: despacho {rule}, {pm} PM por turno y {rules} reglas. {stress_caveat}"
    )
    rendered = {
        "headline": headline,
        "body": body,
        "numbers_used": [
            "on_time_rate_fixed_holdout",
            "on_time_rate_best_holdout",
            "best_max_pm_per_shift",
            "best_rules",
            "delta_throughput_stress",
            "delta_on_time_stress",
        ],
        "stress_caveat": stress_caveat,
    }
    findings = verify(f"{headline} {body}", numbers)
    if findings:
        raise UnverifiedNumbers(findings)
    return rendered


def card_text(
    card: dict[str, Any],
    *,
    mode: Mode | None = None,
    llm_text: str | None = None,
) -> dict[str, Any]:
    """En replay el texto es render_card. En live un borrador del LLM solo entra si verify pasa."""
    resolved: Mode = Settings().MODE if mode is None else mode
    rendered = render_card(card)
    if resolved == "replay" or llm_text is None:
        return rendered
    findings = verify(llm_text, {key: float(value) for key, value in card["numbers"].items()})
    if findings:
        raise UnverifiedNumbers(findings)
    accepted = dict(rendered)
    accepted["body"] = llm_text
    return accepted


def _matches(literal: str, values: list[float], rtol: float) -> bool:
    percent = literal.endswith("%")
    raw = literal[:-1] if percent else literal
    shown = float(raw)
    for value in values:
        if percent:
            scaled = value * 100.0
            if math.isclose(shown, scaled, rel_tol=rtol):
                return True
            if _at_most_one_decimal(raw) and math.isclose(
                shown, round(scaled, 1), rel_tol=0, abs_tol=1e-6
            ):
                return True
        elif math.isclose(shown, value, rel_tol=rtol):
            return True
    return False


def _at_most_one_decimal(raw: str) -> bool:
    if "." not in raw:
        return True
    return len(raw.split(".", 1)[1]) <= 1


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _plain(value: float, *, rtol: float = 1e-4) -> str:
    nearest = round(value)
    if math.isclose(value, nearest, rel_tol=rtol, abs_tol=1e-9):
        return str(int(nearest))
    for decimals in range(12):
        literal = f"{value:.{decimals}f}"
        if math.isclose(float(literal), value, rel_tol=rtol):
            return literal
    return f"{value:.12f}"


def _stress_caveat(numbers: dict[str, float]) -> str:
    throughput = _plain(numbers["delta_throughput_stress"])
    on_time = _percent(numbers["delta_on_time_stress"])
    return (
        f"En estrés el salto de throughput es {throughput} y el de % a tiempo es {on_time}. "
        "El hueco lo lleva el throughput, no el % a tiempo, así que la tarjeta no promete "
        "el mismo salto bajo ese pico."
    )
