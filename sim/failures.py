"""Riesgo de falla por desgaste: logística, tres modos en competencia."""

import math

FAILURE_MODES: tuple[str, ...] = ("MECANICA", "ELECTRICA", "HERRAMIENTA")


def softplus(value: float) -> float:
    if value > 40.0:
        return value
    if value < -40.0:
        return math.exp(value)
    return math.log1p(math.exp(value))


def sigmoid(wear: float, midpoint: float, steepness: float) -> float:
    z = steepness * (wear - midpoint)
    if z >= 40.0:
        return 1.0
    if z <= -40.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def cumulative_hazard(
    wear: float,
    wear_rate: float,
    duration: float,
    base: float,
    midpoint: float,
    steepness: float,
    scale: float,
) -> float:
    """Integral del riesgo por minuto mientras el desgaste crece linealmente."""
    if duration <= 0.0 or base <= 0.0 or scale <= 0.0:
        return 0.0
    amplitude = base * scale
    if wear_rate <= 0.0 or wear >= 1.0:
        return amplitude * sigmoid(min(wear, 1.0), midpoint, steepness) * duration
    t_to_one = (1.0 - wear) / wear_rate
    if duration <= t_to_one:
        wear_end = wear + wear_rate * duration
        integral = softplus(steepness * (wear_end - midpoint))
        integral -= softplus(steepness * (wear - midpoint))
        return amplitude * (integral / steepness) / wear_rate
    integral_to_one = (
        softplus(steepness * (1.0 - midpoint)) - softplus(steepness * (wear - midpoint))
    ) / steepness
    rising = amplitude * integral_to_one / wear_rate
    saturated = amplitude * sigmoid(1.0, midpoint, steepness) * (duration - t_to_one)
    return rising + saturated


def sample_failure(
    rng,
    wear: float,
    wear_rate: float,
    duration: float,
    bases: tuple[float, float, float],
    midpoint: float,
    steepness: float,
    scale: float,
) -> tuple[float, int] | None:
    """Tiempo hasta la primera falla y el índice de modo, o None.

    Cada modo consume un uniforme del generador de la máquina, en orden fijo,
    para que la secuencia no dependa de qué modo gane.
    """
    best_t: float | None = None
    best_mode = 0
    for mode_idx, base in enumerate(bases):
        draw = float(rng.random())
        target = -math.log(max(1e-15, 1.0 - draw))
        hazard_end = cumulative_hazard(wear, wear_rate, duration, base, midpoint, steepness, scale)
        if hazard_end < target:
            continue
        lo = 0.0
        hi = duration
        for _ in range(18):
            mid = (lo + hi) * 0.5
            hazard_mid = cumulative_hazard(wear, wear_rate, mid, base, midpoint, steepness, scale)
            if hazard_mid >= target:
                hi = mid
            else:
                lo = mid
        if best_t is None or hi < best_t:
            best_t = hi
            best_mode = mode_idx
    if best_t is None:
        return None
    return best_t, best_mode
