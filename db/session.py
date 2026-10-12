"""Sesiones de SQLAlchemy. El engine se crea al usarlo, no al importar."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import Settings


def get_engine(url: str | None = None) -> Engine:
    database_url = url or Settings().DATABASE_URL
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )


def session_factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url))
