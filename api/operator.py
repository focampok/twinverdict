"""Tarjeta de operador leída del disco. En replay no hay LLM ni simulador."""

from __future__ import annotations

import json
import math
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.models import PolicyRow, utcnow
from db.session import get_engine
from guard.numbers import UnverifiedNumbers, card_text, verify

RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"
EFFICIENCY_FILE = RESULTS / "efficiency_20261017.json"
MISSING = "—"
DecisionStatus = Literal["approved", "rejected"]


class DecisionLog:
    """Decisiones de aprobar o rechazar. La UI lee esto; la base se actualiza si la fila existe."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, str | None]] = {}

    def record(self, policy_id: str, status: DecisionStatus, reason: str | None) -> None:
        self._rows[policy_id] = {"status": status, "reason": reason}

    def get(self, policy_id: str) -> dict[str, str | None] | None:
        return self._rows.get(policy_id)


def stamp_approval(database_url: str | None, policy_id: str, *, approved: bool) -> None:
    """Escribe approved_at si la fila existe. Sin fila o sin base, no falla."""
    engine = get_engine(database_url)
    try:
        with Session(engine) as session:
            row = session.get(PolicyRow, uuid.UUID(policy_id))
            if row is None:
                return
            row.approved_at = utcnow() if approved else None
            session.commit()
    except SQLAlchemyError:
        return
    finally:
        engine.dispose()


def load_replay(job_id: uuid.UUID) -> dict[str, Any]:
    path = RESULTS / f"replay_{job_id}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return _read_json(str(path))


def winning_policy_id(job_id: str) -> str | None:
    try:
        replay = load_replay(uuid.UUID(job_id))
    except (ValueError, FileNotFoundError, json.JSONDecodeError):
        return None
    policy_id = (replay.get("run") or {}).get("best_policy_id")
    return str(policy_id) if policy_id else None


def operator_context(
    job_id: str,
    mode: str,
    decision: dict[str, str | None] | None,
) -> dict[str, Any]:
    """Contexto de la plantilla. Si verify falla, `error` viene lleno y el texto medido no."""
    page: dict[str, Any] = {
        "mode": mode,
        "error": None,
        "headline": "",
        "body": "",
        "objective_ci": "",
        "policy_id": None,
        "decision_label": _label(decision),
        "decision_reason": None if decision is None else decision.get("reason"),
    }
    try:
        card_id = uuid.UUID(job_id)
        card_path = RESULTS / f"operator_card_{card_id}.json"
        if not card_path.is_file():
            raise FileNotFoundError(card_path)
        card = _read_json(str(card_path))
    except (ValueError, FileNotFoundError, json.JSONDecodeError):
        page["error"] = "This run's card is not on disk."
        return page
    policy_id = winning_policy_id(str(card_id))
    numbers = {key: float(value) for key, value in card["numbers"].items()}
    try:
        rendered = card_text(card, mode="replay" if mode == "replay" else "live")
        objective_ci = _objective_ci(numbers)
        visible = f"{rendered['headline']} {rendered['body']} {objective_ci}"
        findings = verify(visible, numbers)
    except UnverifiedNumbers as exc:
        findings = exc.findings
        rendered = None
        objective_ci = ""
    if findings or rendered is None:
        page["error"] = "The text is hidden. " + " ".join(findings)
        return page
    page.update(
        headline=rendered["headline"],
        body=rendered["body"],
        objective_ci=objective_ci,
        policy_id=str(policy_id) if policy_id else None,
    )
    return page


@lru_cache(maxsize=8)
def _read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _label(decision: dict[str, str | None] | None) -> str:
    if decision is None:
        return "Pending"
    if decision["status"] == "approved":
        return "Approved"
    return "Rejected"


def _objective_ci(numbers: dict[str, float]) -> str:
    fixed = _measured(numbers["objective_fixed_holdout"])
    fixed_low = _measured(numbers["objective_fixed_holdout_ci_low"])
    fixed_high = _measured(numbers["objective_fixed_holdout_ci_high"])
    best = _measured(numbers["objective_best_holdout"])
    best_low = _measured(numbers["objective_best_holdout_ci_low"])
    best_high = _measured(numbers["objective_best_holdout_ci_high"])
    return (
        "Holdout objective interval: fixed rule "
        f"{fixed} [{fixed_low}, {fixed_high}]; "
        f"best policy {best} [{best_low}, {best_high}]."
    )


def load_efficiency() -> dict[str, Any]:
    """JSON oficial de GPU 4. No usa efficiency_20261014.json."""
    if not EFFICIENCY_FILE.is_file():
        raise FileNotFoundError(EFFICIENCY_FILE)
    return _read_json(str(EFFICIENCY_FILE))


def efficiency_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    """Celdas de la tabla. Un valor ausente queda como rayita."""
    rows: list[dict[str, str]] = []
    for method in report.get("methods") or []:
        holdout = method.get("holdout") or {}
        rows.append(
            {
                "name": _display(method.get("name")),
                "train": _num(method.get("best_train")),
                "holdout": _num(holdout.get("objective")),
                "ci": _interval(holdout.get("ci_low"), holdout.get("ci_high")),
                "on_time": _percent(holdout.get("on_time_rate")),
                "sims": _sims(method.get("simulations")),
                "sims_at_90": _sims(method.get("sims_at_target")),
                "source": _display(method.get("note") or method.get("source")),
            }
        )
    return rows


_DISPLAY = {
    "regla fija": "Fixed rule",
    "LLM sin retroalimentación": "LLM without feedback",
    "bucle con retroalimentación": "Loop with feedback",
    "definitivo": "final",
    "vLLM real": "real vLLM",
}


def _display(value: object) -> str:
    text = _text(value)
    return _DISPLAY.get(text, text)


def _text(value: object) -> str:
    if value is None or value == "":
        return MISSING
    return str(value)


def _num(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return MISSING
    return f"{float(value):.4f}"


def _percent(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return MISSING
    return f"{float(value) * 100:.1f}%"


def _sims(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return MISSING
    return str(int(value))


def _interval(low: object, high: object) -> str:
    if _num(low) == MISSING or _num(high) == MISSING:
        return MISSING
    return f"{_num(low)}–{_num(high)}"


def _measured(value: float) -> str:
    nearest = round(value)
    if math.isclose(value, nearest, rel_tol=1e-4, abs_tol=1e-9):
        return str(int(nearest))
    for decimals in range(12):
        literal = f"{value:.{decimals}f}"
        if math.isclose(float(literal), value, rel_tol=1e-4):
            return literal
    return f"{value:.12f}"
