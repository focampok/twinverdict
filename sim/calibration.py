"""Calibración de la curva desgaste → riesgo. Hoy es un stub."""

from dataclasses import dataclass

from sim.config import PlantConfig


@dataclass(frozen=True, slots=True)
class FailureParams:
    midpoint: float
    steepness: float
    base_per_min: tuple[float, float, float]


def fit_failure_curve(dataset_path: str) -> FailureParams:
    """Devuelve los defaults de PlantConfig.

    La curva se calibrará con un dataset público de mantenimiento (AI4I 2020 o
    C-MAPSS). `dataset_path` queda en la firma para esa calibración; hoy no se lee.
    """
    del dataset_path
    config = PlantConfig()
    return FailureParams(
        midpoint=config.failure_midpoint,
        steepness=config.failure_steepness,
        base_per_min=config.failure_base_per_min,
    )
