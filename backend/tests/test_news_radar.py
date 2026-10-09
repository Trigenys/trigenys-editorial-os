from pathlib import Path

from alembic import command
from alembic.config import Config

from editorial_os_api.editorial_intelligence.news_radar import (
    NewsRadarService,
    insight_news_policy,
)
from editorial_os_api.persistence.session import get_session_factory

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def test_insight_news_policy_prioritizes_core_vertical_terms() -> None:
    policy = insight_news_policy()

    assert policy.vertical_key == "trigenys-insight"
    assert policy.version == "2026.10-pilot.1"
    assert {"fr", "en"} == set(policy.eligible_locales)
    assert {"cloud", "cybersecurity", "fintech", "startup"} <= set(
        policy.priority_terms
    )
    assert policy.thresholds.propose_min > policy.thresholds.watch_min


def test_news_radar_is_noop_without_recent_news_signals() -> None:
    _upgrade_schema()
    result = NewsRadarService(get_session_factory()).promote_recent()

    assert result == {
        "signals": 0,
        "clusters": 0,
        "created_runs": 0,
        "results": [],
    }
