"""Salta los tests marcados db si Postgres no responde."""

import pytest
from sqlalchemy import create_engine, text

from config import Settings


def _database_reachable() -> bool:
    try:
        url = Settings().DATABASE_URL
        if not url:
            return False
        engine = create_engine(url, connect_args={"connect_timeout": 2})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
    except Exception:
        return False
    return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    if _database_reachable():
        return
    skip = pytest.mark.skip(reason="DATABASE_URL unset or database unreachable")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)
