from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.config import Settings
from editorial_os_api.db import get_engine

_runtime_settings: Settings | None = None


def configure_session_factory(settings: Settings) -> None:
    """Bind request-time persistence to the runtime's resolved database settings."""

    global _runtime_settings
    _runtime_settings = settings
    get_session_factory.cache_clear()


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(_runtime_settings),
        autoflush=False,
        expire_on_commit=False,
    )
