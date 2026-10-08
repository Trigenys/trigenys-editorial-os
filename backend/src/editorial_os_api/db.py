from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from editorial_os_api.config import Settings, get_settings


@lru_cache
def _engine_for(database_url: str, database_echo: bool) -> Engine:
    return create_engine(
        database_url,
        echo=database_echo,
        pool_pre_ping=True,
    )


def get_engine(settings: Settings | None = None) -> Engine:
    resolved = settings or get_settings()
    return _engine_for(resolved.database_url, resolved.database_echo)


def check_database(settings: Settings | None = None) -> None:
    """Raise if PostgreSQL is not reachable and able to execute a trivial query."""

    with get_engine(settings).connect() as connection:
        connection.execute(text("SELECT 1"))
