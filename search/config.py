"""N, K y R de la búsqueda. Los defaults son los del plan hasta el benchmark."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    N: int = 32
    K: int = 100
    R: int = 8
    TOP_K: int = 5
    HOLDOUT_SEEDS: int = 300
    SEARCH_TARGET_MIN: float = 25
