"""N, K y R para una búsqueda de unos 24 min.

Medido el 13 oct 2026: 796.5 políticas válidas por minuto (Qwen3-8B, concurrencia 32)
y 0.0121 s por simulación en la laptop con 16 workers. El cálculo está en
docs/BENCHMARKS.md. Hace falta SIM_WORKERS=16; con 2 workers el tiempo se multiplica.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    N: int = 48
    K: int = 300
    R: int = 8
    TOP_K: int = 5
    HOLDOUT_SEEDS: int = 300
    SEARCH_TARGET_MIN: float = 25
