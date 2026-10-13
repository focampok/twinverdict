"""Texto de cada ronda: escenario, top-k y fallas a partir de KPIs ya simulados."""

from __future__ import annotations

import json
from typing import Protocol


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
