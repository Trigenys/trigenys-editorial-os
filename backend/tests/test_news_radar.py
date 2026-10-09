from pathlib import Path
from types import SimpleNamespace

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
    assert policy.version == "2026.10-pilot.2"
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


def _signal(title: str):
    return SimpleNamespace(
        title=title,
        canonical_url="https://example.test/article",
        extracted_payload={},
    )


def _source(*, key: str, region: str):
    return SimpleNamespace(
        config={
            "source_key": key,
            "region": region,
            "discovery_weight": 90,
        }
    )


def test_news_radar_rejects_global_off_topic_reuters_items() -> None:
    service = NewsRadarService(get_session_factory())
    reuters = _source(key="reuters", region="global")

    assert service._eligible_signal(
        _signal("Prince Harry says he struggled with his future in the royal family"),
        reuters,
    ) is False
    assert service._eligible_signal(
        _signal("Geely enters Canadian market and plans vehicle sales in 2027"),
        reuters,
    ) is False


def test_news_radar_keeps_global_vertical_technology_items() -> None:
    service = NewsRadarService(get_session_factory())
    reuters = _source(key="reuters", region="global")

    assert service._eligible_signal(
        _signal("China vows to curb tech bubbles and keep AI risks in check"),
        reuters,
    ) is True
    assert service._eligible_signal(
        _signal("Cloud provider discloses major data breach after cyberattack"),
        reuters,
    ) is True


def test_news_radar_keeps_african_business_and_specialist_cyber_items() -> None:
    service = NewsRadarService(get_session_factory())

    assert service._eligible_signal(
        _signal("Cameroon bank launches new SME investment platform"),
        _source(key="ecomatin", region="cameroon"),
    ) is True
    assert service._eligible_signal(
        _signal("Cisco warns of critical flaws allowing Nexus switch takeover"),
        _source(key="bleeping-computer", region="global"),
    ) is True


def test_news_radar_uses_token_boundaries_for_short_ai_term() -> None:
    service = NewsRadarService(get_session_factory())

    assert service._term_hits("chairman said plans remain unchanged", ("ai",)) == set()
    assert service._term_hits("new AI rules take effect", ("ai",)) == {"ai"}
