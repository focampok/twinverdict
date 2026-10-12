"""Configuración por variables de entorno. Nunca secretos en el repo."""

from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import field_validator
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
    LLM_BASE_URL: str = "http://localhost:8001/v1"
    LLM_MODEL: str = "mock"
    LLM_API_KEY: str = "mock"
    ADMIN_TOKEN: str = ""
    SIM_WORKERS: int = 2

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)
