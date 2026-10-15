"""Configuración por variables de entorno. Nunca secretos en el repo."""

from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Convierte el esquema de Railway (postgresql:// o postgres://) a psycopg.

    Conserva usuario, host, ruta y parámetros (por ejemplo sslmode).
    """
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme == "postgresql+psycopg":
        return url
    if scheme == "postgres":
        scheme = "postgresql"
    if scheme == "postgresql":
        return urlunsplit(
            ("postgresql+psycopg", parts.netloc, parts.path, parts.query, parts.fragment)
        )
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://planta:planta@localhost:5432/planta"
    MODE: Literal["live", "replay"] = "live"
    # Corrida oficial de la demo. c43bd2f0 queda versionada como histórico.
    REPLAY_JOB_ID: str = "285d1787-5d7c-464a-9897-4c585663f088"
    LLM_BASE_URL: str = "http://localhost:8001/v1"
    # Qwen3-8B es el modelo por defecto. Qwen3-32B se evalúa por calidad de política.
    LLM_MODEL: str = "Qwen/Qwen3-8B"
    LLM_API_KEY: str = "mock"
    # Muestreo de búsqueda. El cliente los manda siempre: si se omiten, vLLM usa el
    # generation_config del modelo (Qwen3-8B: temperature 0.6, top_k 20, top_p 0.95).
    # top_k=-1 es abierto: vLLM considera todos los tokens.
    LLM_TEMPERATURE: float = Field(default=1.0, ge=0)
    LLM_TOP_P: float = Field(default=0.95, ge=0, le=1)
    LLM_TOP_K: int = Field(default=-1, ge=-1)
    ADMIN_TOKEN: str = ""
    SIM_WORKERS: int = 2

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)
