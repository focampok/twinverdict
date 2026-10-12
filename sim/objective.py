"""Objetivo compuesto. Mayor es mejor. Los pesos viven en JSON para poder editarlos."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_WEIGHTS_PATH = Path(__file__).with_name("objective_weights.json")


class ObjectiveWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    throughput: float = 1.0
    on_time_rate: float = 1.0
    unplanned_downtime_h: float = 1.0
    planned_downtime_h: float = 0.5
    maintenance_cost: float = 0.5
    ref_throughput: float = 400.0
    ref_on_time_rate: float = 1.0
    ref_unplanned_downtime_h: float = 40.0
    ref_planned_downtime_h: float = 20.0
    ref_maintenance_cost: float = 10000.0


def load_objective_weights(path: Path | None = None) -> ObjectiveWeights:
    raw = json.loads((path or _WEIGHTS_PATH).read_text())
    return ObjectiveWeights.model_validate(raw)


def _over(value: float, scale: float) -> float:
    if scale == 0:
        return 0.0
    return value / scale


def composite_objective(
    metrics: dict[str, float],
    weights: ObjectiveWeights | None = None,
) -> float:
    """Combina KPIs ya normalizados por una escala de referencia. Mayor es mejor."""
    w = weights or load_objective_weights()
    unplanned = _over(metrics["unplanned_downtime_h"], w.ref_unplanned_downtime_h)
    planned = _over(metrics["planned_downtime_h"], w.ref_planned_downtime_h)
    return (
        w.throughput * _over(metrics["throughput"], w.ref_throughput)
        + w.on_time_rate * _over(metrics["on_time_rate"], w.ref_on_time_rate)
        - w.unplanned_downtime_h * unplanned
        - w.planned_downtime_h * planned
        - w.maintenance_cost * _over(metrics["maintenance_cost"], w.ref_maintenance_cost)
    )
