from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from editorial_os_api.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


def check_database() -> None:
    """Raise if PostgreSQL is not reachable and able to execute a trivial query."""

    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
