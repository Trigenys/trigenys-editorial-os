from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from editorial_os_api.persistence.models import Source
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.scout.news_registry import (
    INSIGHT_VERTICAL_KEY,
    NEWS_REGISTRY_ID,
    NEWS_SOURCES,
    seed_news_sources,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def test_news_registry_has_expected_coverage_and_unique_keys() -> None:
    assert len(NEWS_SOURCES) == 24
    assert len({source.key for source in NEWS_SOURCES}) == 24

    regions = {source.region for source in NEWS_SOURCES}
    assert {"cameroon", "africa", "global", "global-emerging-markets"} <= regions

    names = {source.registration.name for source in NEWS_SOURCES}
    assert {
        "EcoMatin",
        "Digital Business Africa",
        "TechCabal",
        "MyBroadband",
        "Reuters",
        "BleepingComputer",
    } <= names

    for source in NEWS_SOURCES:
        assert source.registration.redact_raw_content is True
        assert source.registration.config["registry_id"] == NEWS_REGISTRY_ID
        assert source.registration.config["store_full_text"] is False
        assert source.registration.config["scrape_policy"] == "respect-robots-and-terms"
        assert 1 <= source.discovery_weight <= 100
        assert source.roles
        assert source.topics


def test_news_source_seed_is_idempotent() -> None:
    _upgrade_schema()

    first = seed_news_sources(get_session_factory())
    second = seed_news_sources(get_session_factory())

    assert first == second
    assert set(first) == {source.key for source in NEWS_SOURCES}

    with get_session_factory()() as session:
        rows = list(
            session.scalars(
                select(Source).where(
                    Source.config["registry_id"].astext == NEWS_REGISTRY_ID
                )
            )
        )
        count = session.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.config["registry_id"].astext == NEWS_REGISTRY_ID)
        )

    assert count == len(NEWS_SOURCES)
    assert len(rows) == len(NEWS_SOURCES)
    assert all(row.vertical_keys == [INSIGHT_VERTICAL_KEY] for row in rows)
    assert all(row.config["source_key"] for row in rows)
