"""Texto de cada ronda: escenario, top-k y fallas a partir de KPIs ya simulados."""

from __future__ import annotations

import json
from typing import Protocol

from policy.schema import (
    DEFAULT_PM_THRESHOLD,
    MACHINES,
    Policy,
    fixed_rule_policy,
    parse_policy,
)
from sim.config import PlantConfig

# El despacho lee los pesos en WEIGHTED y en CRITICAL_RATIO (sim/dispatch.py).
# EDD y SPT no. version no entra en ninguna decisión.
_RULES_USING_WEIGHTS = frozenset({"WEIGHTED", "CRITICAL_RATIO"})


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


def simulator_key(policy: Policy) -> tuple:
    """Lo que el simulador lee. Dos políticas con la misma clave puntúan igual.

    Umbral ausente vale el default 0.75, igual que `threshold_for`. Los pesos
    entran solo si la regla de despacho los usa. `version` queda fuera.
    """
    thresholds = tuple(policy.maintenance.threshold_for(machine) for machine in MACHINES)
    weights = None
    if policy.dispatch.rule in _RULES_USING_WEIGHTS:
        stored = policy.dispatch.weights
        assert stored is not None
        weights = (stored.due_date, stored.wear_risk, stored.setup)
    rules = []
    for rule in policy.rules:
        cond = rule.cond
        action = rule.then_
        payload = action.model_dump(mode="json")
        rules.append(
            (
                cond.machine,
                cond.wear_gt,
                cond.urgent_order_waiting,
                cond.queue_len_gt,
                cond.product_waiting,
                tuple(sorted(payload.items())),
            )
        )
    return (
        policy.dispatch.rule,
        thresholds,
        policy.maintenance.max_pm_per_shift,
        tuple(rules),
        weights,
    )


def dedupe_top(ranked: list[_Scored], k: int) -> list[_Scored]:
    """Las k mejores políticas que el simulador distingue, en el orden recibido."""
    chosen: list[_Scored] = []
    seen: set[tuple] = set()
    for item in ranked:
        key = simulator_key(parse_policy(item.policy_json()))
        if key in seen:
            continue
        seen.add(key)
        chosen.append(item)
        if len(chosen) == k:
            break
    return chosen


def _prompt_json(item: _Scored) -> str:
    """JSON que ve el modelo: version 1 y los umbrales que el simulador usaría."""
    policy = parse_policy(item.policy_json())
    body = policy.model_dump(mode="json", by_alias=True)
    body["version"] = 1
    body["maintenance"]["pm_wear_threshold"] = {
        machine: policy.maintenance.threshold_for(machine) for machine in MACHINES
    }
    return json.dumps(body, sort_keys=True, ensure_ascii=False)


def _ask(kind: str, *, has_top: bool) -> str:
    if kind == "local" and has_top:
        return (
            "Sobre politica_1, haz de 2 a 4 cambios locales. "
            "Puedes cambiar la regla de despacho, max_pm_per_shift y rules, "
            "además de pm_wear_threshold. "
            "Escribe un umbral explícito para M1, M2, M3, M4 y M5. Fija version=1."
        )
    if kind == "free" and has_top:
        return (
            "Propón una política libre y distinta al top-k en lo que lee el simulador: "
            "regla, umbrales, max_pm_per_shift y rules. "
            "Puedes cambiar la regla de despacho, max_pm_per_shift y rules. "
            "Escribe un umbral explícito para M1, M2, M3, M4 y M5. Fija version=1."
        )
    if kind not in {"local", "free"}:
        raise ValueError(f"tipo de propuesta desconocido: {kind}")
    return (
        "Propón una política con version=1. "
        "Puedes cambiar la regla de despacho, max_pm_per_shift y rules. "
        "Escribe un umbral explícito para M1, M2, M3, M4 y M5."
    )


def build_search_prompt(scenario: str, top: list[_Scored], *, kind: str = "local") -> str:
    """Una petición, una política. `kind` elige edición local o propuesta libre.

    La ronda parte las N peticiones entre los dos textos. Con N=48 son 24 y 24.
    """
    midpoint = PlantConfig().failure_midpoint
    lines = [f"escenario: {scenario}"]
    if not top:
        lines.append("No hay políticas previas.")
    else:
        for index, item in enumerate(top, start=1):
            kpis = json.dumps(_public_kpis(item.kpis), sort_keys=True)
            lines.append(
                f"politica_{index} objetivo={item.objective:.6f} kpis={kpis} "
                f"fallas={failure_note(item.kpis)} json={_prompt_json(item)}"
            )
    lines.append(
        "pm_wear_threshold: un número por máquina M1 a M5, entre 0.30 y 0.95. "
        f"El ausente vale {DEFAULT_PM_THRESHOLD:.2f}. "
        f"El desgaste donde se concentran las fallas está cerca de {midpoint:.2f}, "
        "según la calibración."
    )
    lines.append(_ask(kind, has_top=bool(top)))
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
