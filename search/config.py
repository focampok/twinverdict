"""N, K y R de la búsqueda.

El perfil default usa K=180: a 0.0212 s/sim sostenidos (job 78fea53a) una
búsqueda con 385 políticas cabe en unos 24.5 min. El perfil final sube K a 300
si sobra tiempo. El perfil smoke es el de los tests. Hace falta SIM_WORKERS=16
en la laptop. El cálculo está en docs/BENCHMARKS.md.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

PROFILES: dict[str, dict[str, int]] = {
    "default": {"N": 48, "K": 180, "R": 8, "TOP_K": 5, "HOLDOUT_SEEDS": 300},
    "final": {"N": 48, "K": 300, "R": 8, "TOP_K": 5, "HOLDOUT_SEEDS": 300},
    "smoke": {"N": 2, "K": 2, "R": 2, "TOP_K": 2, "HOLDOUT_SEEDS": 0},
}


class SearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    N: int = 48
    K: int = 180
    R: int = 8
    TOP_K: int = 5
    HOLDOUT_SEEDS: int = 300
    SEARCH_TARGET_MIN: float = 25
    profile: str = "default"

    @classmethod
    def from_profile(cls, name: str) -> "SearchConfig":
        try:
            values = PROFILES[name]
        except KeyError:
            known = ", ".join(sorted(PROFILES))
            raise ValueError(f"perfil desconocido: {name}. Perfiles: {known}") from None
        return cls(profile=name, **values)
