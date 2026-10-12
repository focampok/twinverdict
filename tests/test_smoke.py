import importlib

from config import Settings, normalize_database_url

PACKAGES = [
    "sim",
    "policy",
    "search",
    "llm",
    "eval",
    "baselines",
    "guard",
    "api",
    "ui",
    "db",
    "worker",
    "bench",
]


def test_packages_import() -> None:
    for name in PACKAGES:
        importlib.import_module(name)


def test_database_url_normalization_from_railway() -> None:
    settings = Settings(
        DATABASE_URL="postgresql://planta:planta@example:5432/planta?sslmode=require",
    )
    assert (
        settings.DATABASE_URL
        == "postgresql+psycopg://planta:planta@example:5432/planta?sslmode=require"
    )


def test_database_url_postgres_alias_keeps_query() -> None:
    normalized = normalize_database_url("postgres://u:p@h:5432/d?sslmode=require")
    assert normalized == "postgresql+psycopg://u:p@h:5432/d?sslmode=require"


def test_database_url_already_normalized_is_unchanged() -> None:
    url = "postgresql+psycopg://planta:planta@localhost:5432/planta"
    assert normalize_database_url(url) == url
