"""KPIs de una corrida. Todos son float para que el dict sea picklable y comparable."""

from sim.model import SimResult


def kpis_from_result(result: SimResult, wall_s: float) -> dict[str, float]:
    completed = result.orders_completed
    on_time_rate = (result.on_time / completed) if completed else 0.0
    return {
        "throughput": float(result.orders_completed),
        "on_time_rate": float(on_time_rate),
        "unplanned_downtime_h": result.unplanned_min / 60.0,
        "planned_downtime_h": result.planned_min / 60.0,
        "maintenance_cost": float(result.maintenance_cost),
        "orders_created": float(result.orders_created),
        "orders_completed": float(result.orders_completed),
        "orders_wip": float(result.orders_wip),
        "failures_total": float(sum(result.failures)),
        "failures_by_mode_MECANICA": float(result.failures[0]),
        "failures_by_mode_ELECTRICA": float(result.failures[1]),
        "failures_by_mode_HERRAMIENTA": float(result.failures[2]),
        "pm_count": float(result.pm_count),
        "sim_wall_s": float(wall_s),
    }
