from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from editorial_os_api.config import Settings, get_settings


@lru_cache
def _engine_for(database_url: str, database_echo: bool) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("postgresql+pg8000://"):
        # Hyperdrive already owns connection pooling. A Python Worker isolate may
        # serve multiple requests, but sockets must not leak from one request
        # context into another. NullPool keeps SQLAlchemy's Engine reusable while
        # opening and closing the Hyperdrive connection within each request.
        connect_args["ssl_context"] = False
        return create_engine(
            database_url,
            echo=database_echo,
            poolclass=NullPool,
            connect_args=connect_args,
        )

    return create_engine(
        database_url,
        echo=database_echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def get_engine(settings: Settings | None = None) -> Engine:
    resolved = settings or get_settings()
    return _engine_for(resolved.database_url, resolved.database_echo)


def check_database(settings: Settings | None = None) -> None:
    """Raise if PostgreSQL is not reachable and able to execute a trivial query."""

    with get_engine(settings).connect() as connection:
        connection.execute(text("SELECT 1"))
