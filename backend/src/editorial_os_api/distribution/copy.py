from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from editorial_os_api.distribution.contracts import ChannelVariant

_CHANNEL_LIMITS: dict[str, int] = {
    "x": 280,
    "twitter": 280,
    "linkedin": 3000,
    "linkedin-page": 3000,
    "instagram": 2200,
    "facebook": 5000,
    "threads": 500,
    "bluesky": 300,
}


@dataclass(frozen=True)
class CanonicalArticle:
    title: str
    deck: str | None
    url: str
    locale: str


class ChannelCopyGenerator:
    """Deterministic baseline that can later be replaced by a model-backed adapter."""

    def generate(
        self,
        article: CanonicalArticle,
        *,
        channel: str,
        integration_id: str,
        scheduled_at: datetime | None = None,
        settings: dict[str, object] | None = None,
    ) -> ChannelVariant:
        normalized = channel.strip().lower()
        limit = _CHANNEL_LIMITS.get(normalized, 2000)

        parts = [article.title.strip()]
        if article.deck and article.deck.strip():
            parts.append(article.deck.strip())
        parts.append(article.url.strip())
        content = "\n\n".join(parts)
        content = _truncate_preserving_url(content, article.url, limit)

        return ChannelVariant(
            channel=normalized,
            integration_id=integration_id,
            content=content,
            settings=dict(settings or {}),
            scheduled_at=scheduled_at,
        )


def _truncate_preserving_url(content: str, url: str, limit: int) -> str:
    if len(content) <= limit:
        return content
    suffix = f"…\n\n{url}"
    available = max(0, limit - len(suffix))
    return f"{content[:available].rstrip()}{suffix}"
