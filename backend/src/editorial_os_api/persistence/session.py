from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.config import Settings, get_settings
from editorial_os_api.db import get_engine


@lru_cache
def _session_factory_for(
    database_url: str,
    database_echo: bool,
) -> sessionmaker[Session]:
    settings = Settings(
        database_url=database_url,
        database_echo=database_echo,
    )
    return sessionmaker(
        bind=get_engine(settings),
        autoflush=False,
        expire_on_commit=False,
    )


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    resolved = settings or get_settings()
    return _session_factory_for(resolved.database_url, resolved.database_echo)
