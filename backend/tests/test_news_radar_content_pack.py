"""News Radar and downstream Content Agent must agree on vertical-pack versions."""

from editorial_os_api.editorial_intelligence.news_radar import (
    NEWS_RADAR_VERTICAL_VERSION,
    insight_news_policy,
)
from editorial_os_api.vertical_packs.builtin import get_builtin_vertical_pack


def test_news_radar_version_has_matching_french_first_content_pack() -> None:
    policy = insight_news_policy()
    pack = get_builtin_vertical_pack(policy.vertical_key, NEWS_RADAR_VERTICAL_VERSION)
    assert pack.key == policy.vertical_key
    assert pack.version == policy.version
    assert pack.default_locale == "fr"
    assert pack.supports(locale="fr", content_format="article")
    assert pack.metadata["publication_mode"] == "payload-staging-only"
