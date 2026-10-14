"""Parámetros de la planta. Todo el azar de una corrida sale de la semilla, no de aquí."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlantConfig:
    """Unidades en minutos.

    La forma desgaste → riesgo es el corte AI4I del 14 oct 2026: midpoint 0.95 y
    steepness 18. El nivel por minuto no se calibró y sigue siendo supuesto de planta.
    Los objetivos medidos antes de ese corte no se comparan con los de después.
    """

    horizon_min: float = 7 * 24 * 60
    shift_min: float = 8 * 60
    process_mean: tuple[tuple[float, ...], ...] = (
        (8.0, 9.0, 7.0, 8.0, 6.0),
        (11.0, 8.0, 10.0, 9.0, 12.0),
        (7.0, 6.0, 8.0, 11.0, 9.0),
    )
    process_sigma: float = 0.2
    setup_min: tuple[float, ...] = (4.0, 5.0, 3.0, 4.0, 6.0)
    arrival_mean_min: float = 12.0
    product_mix: tuple[float, float, float] = (0.4, 0.35, 0.25)
    slack_low_min: float = 240.0
    slack_high_min: float = 960.0
    urgent_slack_min: float = 90.0
    wear_per_min: tuple[tuple[float, ...], ...] = (
        (0.004, 0.005, 0.0035, 0.004, 0.003),
        (0.006, 0.0045, 0.005, 0.004, 0.006),
        (0.003, 0.0035, 0.004, 0.006, 0.0045),
    )
    failure_midpoint: float = 0.95
    failure_steepness: float = 18.0
    failure_base_per_min: tuple[float, float, float] = (0.0015, 0.0012, 0.0018)
    failure_rate_scale: float = 1.0
    repair_mean_min: tuple[float, float, float] = (40.0, 25.0, 18.0)
    repair_cost: tuple[float, float, float] = (450.0, 280.0, 160.0)
    pm_duration_min: float = 12.0
    pm_cost: float = 70.0
    demand_scale: float = 1.0

    def wear_scale(self) -> float:
        peak = 0.0
        for row in self.wear_per_min:
            for value in row:
                if value > peak:
                    peak = value
        return peak or 1.0
