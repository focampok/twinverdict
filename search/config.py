"""N, K y R de la búsqueda.

K=300 sale del ritmo de ráfaga (0.0121 s por simulación, unos 24 min). El job
78fea53a sostuvo 0.0212 s por simulación y tardó 40.8 min. Para 20 a 30 min a ese
ritmo, K=180. El detalle está en docs/BENCHMARKS.md. Hace falta SIM_WORKERS=16.
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
