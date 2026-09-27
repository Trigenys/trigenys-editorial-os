from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from editorial_os_api.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def _current_revision() -> str | None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def test_migration_round_trip() -> None:
    config = _alembic_config()
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()

    command.upgrade(config, "head")
    assert _current_revision() == head

    command.downgrade(config, "base")
    assert _current_revision() is None

    command.upgrade(config, "head")
    assert _current_revision() == head
