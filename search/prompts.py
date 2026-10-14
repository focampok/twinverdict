"""Texto de cada ronda: escenario, top-k y fallas a partir de KPIs ya simulados."""

from __future__ import annotations

import json
from typing import Protocol

from policy.schema import fixed_rule_policy


class _Scored(Protocol):
    objective: float
    kpis: dict[str, float]

    def policy_json(self) -> dict: ...


def failure_note(kpis: dict[str, float]) -> str:
    """Paro agregado y órdenes tardías. Los KPIs no separan el paro por máquina."""
    completed = float(kpis.get("orders_completed", 0.0))
    late = completed * (1.0 - float(kpis.get("on_time_rate", 0.0)))
    downtime = float(kpis.get("unplanned_downtime_h", 0.0))
    failures = float(kpis.get("failures_total", 0.0))
    return (
        f"paro_no_planificado_h={downtime:.4f} (agregado, sin desglose por máquina); "
        f"ordenes_tardias={late:.2f} de {completed:.0f}; fallas={failures:.0f}"
    )


def _public_kpis(kpis: dict[str, float]) -> dict[str, float]:
    hidden = {"sim_wall_s"}
    return {key: kpis[key] for key in sorted(kpis) if key not in hidden}


def build_search_prompt(scenario: str, top: list[_Scored]) -> str:
    lines = [f"escenario: {scenario}"]
    if not top:
        lines.append("No hay políticas previas.")
    for index, item in enumerate(top, start=1):
        body = json.dumps(item.policy_json(), sort_keys=True, ensure_ascii=False)
        kpis = json.dumps(_public_kpis(item.kpis), sort_keys=True)
        lines.append(
            f"politica_{index} objetivo={item.objective:.6f} kpis={kpis} "
            f"fallas={failure_note(item.kpis)} json={body}"
        )
    lines.append("Propón una política distinta que mejore el objetivo.")
    return "\n".join(lines)


def build_oneshot_prompt(scenario: str) -> str:
    """Prompt fijo para la línea base sin retroalimentación (Prompt 16).

    Lleva el escenario, la regla fija como referencia y las reglas del schema. No
    lleva objetivos, KPIs ni fallas de candidatas anteriores: el LLM propone a
    ciegas. Es el punto de la línea base, y la razón del nombre: sin eso no se
    puede decir cuánto aporta el bucle.
    """
    reference = json.dumps(
        fixed_rule_policy().model_dump(mode="json", by_alias=True),
        sort_keys=True,
        ensure_ascii=False,
    )
    return "\n".join(
        [
            f"escenario: {scenario}",
            f"política de referencia (regla fija): {reference}",
            "Devuelve una política distinta en JSON con estos campos:",
            "- maintenance.pm_wear_threshold: por máquina M1 a M5, entre 0.30 y 0.95",
            "- maintenance.max_pm_per_shift: entero entre 0 y 3",
            "- dispatch.rule: EDD, SPT, WEIGHTED o CRITICAL_RATIO",
            "- dispatch.weights (due_date, wear_risk, setup): solo con WEIGHTED, suman 1",
            "- rules: hasta 5 reglas con if/then de mantenimiento y despacho",
            "Propón una política distinta.",
        ]
    )
