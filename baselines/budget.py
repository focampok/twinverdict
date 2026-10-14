"""Presupuesto de entrenamiento compartido por el bucle y las líneas base.

Una búsqueda del perfil gasta K simulaciones en la política 0 (la regla fija) y
N*R*K en las propuestas: K + N*R*K. Las líneas base (Optuna en el Prompt 15, LLM
sin retroalimentación en el 16) gastan exactamente el mismo número, con las
mismas semillas de entrenamiento y el mismo escenario. Si el presupuesto cambia
de un método a otro, la comparación no dice nada.
"""

from __future__ import annotations

from search.config import SearchConfig


def total_train_sims(config: SearchConfig) -> int:
    """K de la política 0 más N*R*K de las propuestas, cada una en K semillas."""
    return config.K + config.N * config.R * config.K


def train_seeds(config: SearchConfig, rng_seed: int) -> list[int]:
    """Las semillas de entrenamiento de run_search: range(seed, seed + K)."""
    return list(range(rng_seed, rng_seed + config.K))
