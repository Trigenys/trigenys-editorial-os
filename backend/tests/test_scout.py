from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from alembic import command
from alembic.config import Config
import httpx
import pytest
from sqlalchemy import func, select

from editorial_os_api.domain.enums import (
    EvidenceTier,
    SourceFailureKind,
    SourceHealthStatus,
    SourceKind,
)
from editorial_os_api.persistence.models import SourceFetch, SourceItem
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.scout import (
    FetchPolicy,
    ScoutAgent,
    SourceAdapterError,
    SourceRegistry,
)
from editorial_os_api.scout.adapters import (
    Crawl4AIExtractionAdapter,
    HttpPageExtractor,
    RSSHubAdapter,
    RssAtomAdapter,
)
from editorial_os_api.scout.contracts import (
    ManualUrlInput,
    PageExtraction,
    RawFetchBatch,
    SourceRegistration,
    SourceSnapshot,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]

RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Fixture News</title>
    <item>
      <title>  Same   story  </title>
      <guid>fixture-1</guid>
      <link>https://Example.com/story/?utm_source=rss&amp;b=2&amp;a=1#frag</link>
      <description>  A   normalized   summary. </description>
      <pubDate>Sun, 28 Sep 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _registry() -> SourceRegistry:
    _upgrade_schema()
    return SourceRegistry(get_session_factory())


def _register(
    *,
    kind: SourceKind = SourceKind.RSS,
    base_url: str | None = "https://feeds.example.test/news.xml",
    vertical_keys: list[str] | None = None,
    redact_raw_content: bool = False,
    config: dict[str, object] | None = None,
    policy: FetchPolicy | None = None,
) -> SourceSnapshot:
    return _registry().register(
        SourceRegistration(
            name="Fixture source",
            kind=kind,
            base_url=base_url,
            trust_tier=EvidenceTier.E2,
            default_evidence_tier=EvidenceTier.E2,
            locale="en",
            vertical_keys=["technology"] if vertical_keys is None else vertical_keys,
            fetch_policy=policy or FetchPolicy(interval_seconds=60),
            retention_days=7,
            redact_raw_content=redact_raw_content,
            config=config or {},
        )
    )


def _feed_client(payload: str = RSS_FIXTURE) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=payload,
            headers={"content-type": "application/rss+xml"},
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_source_registry_filters_by_vertical_and_due_state() -> None:
    registry = _registry()
    tech = registry.register(
        SourceRegistration(
            name="Tech",
            kind=SourceKind.RSS,
            base_url="https://example.test/tech.xml",
            vertical_keys=["technology"],
        )
    )
    registry.register(
        SourceRegistration(
            name="Gaming",
            kind=SourceKind.RSS,
            base_url="https://example.test/gaming.xml",
            vertical_keys=["gaming"],
        )
    )

    eligible = registry.eligible_sources(
        "technology",
        now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
    )

    assert [source.id for source in eligible] == [tech.id]


def test_same_feed_item_twice_produces_one_canonical_signal_and_two_fetches() -> None:
    source = _register()
    agent = ScoutAgent(get_session_factory())
    client = _feed_client()
    adapter = RssAtomAdapter(client)

    first = agent.ingest(source.id, adapter, force=True)
    second = agent.ingest(source.id, adapter, force=True)

    assert first.status == "SUCCEEDED"
    assert first.created_count == 1
    assert second.status == "SUCCEEDED"
    assert second.created_count == 0
    assert second.updated_count == 1

    with get_session_factory()() as session:
        item_count = session.scalar(
            select(func.count())
            .select_from(SourceItem)
            .where(SourceItem.source_id == source.id)
        )
        fetch_count = session.scalar(
            select(func.count())
            .select_from(SourceFetch)
            .where(SourceFetch.source_id == source.id)
        )
        item = session.scalar(
            select(SourceItem).where(SourceItem.source_id == source.id)
        )
        fetches = list(
            session.scalars(
                select(SourceFetch)
                .where(SourceFetch.source_id == source.id)
                .order_by(SourceFetch.started_at, SourceFetch.id)
            )
        )

    assert item_count == 1
    assert fetch_count == 2
    assert item is not None
    assert item.canonical_url == "https://example.com/story?a=1&b=2"
    assert item.title == "Same story"
    assert item.raw_content is None
    assert item.provenance["source_id"] == str(source.id)
    assert item.source_fetch_id == fetches[-1].id
    assert all(fetch.raw_payload == RSS_FIXTURE for fetch in fetches)
    assert all(fetch.raw_sha256 is not None for fetch in fetches)


def test_redacted_source_keeps_fetch_hash_but_not_raw_payload() -> None:
    source = _register(redact_raw_content=True)
    client = _feed_client()
    result = ScoutAgent(get_session_factory()).ingest(
        source.id,
        RssAtomAdapter(client),
        force=True,
    )

    assert result.status == "SUCCEEDED"
    with get_session_factory()() as session:
        fetch = session.get(SourceFetch, result.fetch_id)
        assert fetch is not None
        assert fetch.raw_payload is None
        assert fetch.raw_sha256 is not None


class RetryableFailureAdapter:
    name = "retryable-fixture"

    def requested_url(self, source: SourceSnapshot) -> str:
        return source.base_url or "https://example.test/"

    def fetch(self, source: SourceSnapshot) -> RawFetchBatch:
        del source
        raise SourceAdapterError(
            "temporary timeout",
            kind=SourceFailureKind.TIMEOUT,
            retryable=True,
        )


class TerminalFailureAdapter:
    name = "terminal-fixture"

    def requested_url(self, source: SourceSnapshot) -> str:
        return source.base_url or "https://example.test/"

    def fetch(self, source: SourceSnapshot) -> RawFetchBatch:
        del source
        raise SourceAdapterError(
            "invalid permanent configuration",
            kind=SourceFailureKind.CONFIGURATION,
            retryable=False,
        )


def test_retryable_failure_degrades_source_and_applies_backoff() -> None:
    source = _register(
        policy=FetchPolicy(
            interval_seconds=60,
            max_backoff_seconds=600,
            max_failures_before_pause=3,
        )
    )
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

    result = ScoutAgent(get_session_factory()).ingest(
        source.id,
        RetryableFailureAdapter(),
        force=True,
        now=now,
    )

    assert result.status == "FAILED"
    assert result.failure_kind == SourceFailureKind.TIMEOUT.value
    assert result.retryable is True

    updated = _registry().get(source.id)
    assert updated.health_status is SourceHealthStatus.DEGRADED
    assert updated.consecutive_failures == 1
    assert updated.next_fetch_at == datetime(2026, 9, 28, 12, 1, tzinfo=UTC)


def test_terminal_failure_pauses_source() -> None:
    source = _register()

    result = ScoutAgent(get_session_factory()).ingest(
        source.id,
        TerminalFailureAdapter(),
        force=True,
    )

    assert result.status == "FAILED"
    assert result.retryable is False
    updated = _registry().get(source.id)
    assert updated.health_status is SourceHealthStatus.PAUSED
    assert updated.next_fetch_at is None


def test_rsshub_adapter_builds_route_without_leaking_into_domain() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            text=RSS_FIXTURE,
            headers={"content-type": "application/rss+xml"},
            request=request,
        )

    source = _register(
        kind=SourceKind.RSSHUB,
        base_url="https://rsshub.example.test",
        config={"route": "/github/issue/Trigenys/trigenys-editorial-os"},
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = ScoutAgent(get_session_factory()).ingest(
        source.id,
        RSSHubAdapter(client),
        force=True,
    )

    assert result.created_count == 1
    assert seen_urls == [
        "https://rsshub.example.test/github/issue/Trigenys/trigenys-editorial-os"
    ]


class FixturePageExtractor:
    name = "fixture-page"

    def extract(self, url: str, *, timeout_seconds: float) -> PageExtraction:
        assert timeout_seconds > 0
        return PageExtraction(
            requested_url=url,
            final_url=f"{url}?utm_source=manual",
            title="Manual page",
            text="Useful page text",
            raw_payload="<html><title>Manual page</title>Useful page text</html>",
            http_status=200,
            content_type="text/html",
            metadata={"extractor": self.name},
        )


def test_manual_url_ingestion_uses_same_canonical_pipeline() -> None:
    source = _register(
        kind=SourceKind.MANUAL,
        base_url=None,
        vertical_keys=[],
    )
    result = ScoutAgent(get_session_factory()).ingest_manual_url(
        source.id,
        ManualUrlInput(url="https://example.com/manual", locale="fr"),
        extractor=FixturePageExtractor(),
    )

    assert result.status == "SUCCEEDED"
    assert result.created_count == 1
    with get_session_factory()() as session:
        item = session.scalar(
            select(SourceItem).where(SourceItem.source_id == source.id)
        )
        assert item is not None
        assert item.canonical_url == "https://example.com/manual"
        assert item.locale == "fr"
        assert item.extracted_payload["body"] == "Useful page text"


class FakeCrawlResult:
    success = True
    markdown = "# Extracted\n\nBody"
    html = "<h1>Extracted</h1><p>Body</p>"
    url = "https://example.com/article"
    metadata = {"title": "Extracted"}


class FakeCrawler:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        del exc_type, exc, traceback

    async def arun(self, *, url: str) -> FakeCrawlResult:
        assert url == "https://example.com/article"
        return FakeCrawlResult()


def test_crawl4ai_adapter_is_optional_and_injectable() -> None:
    adapter = Crawl4AIExtractionAdapter(crawler_factory=FakeCrawler)

    extraction = adapter.extract(
        "https://example.com/article",
        timeout_seconds=5,
    )

    assert extraction.text == "# Extracted\n\nBody"
    assert extraction.title == "Extracted"
    assert extraction.metadata["extractor"] == "crawl4ai"


def test_http_page_extractor_baseline_is_replaceable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><head><title>Fixture</title></head><body>Hello world</body></html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    extraction = HttpPageExtractor(client).extract(
        "https://example.test/page",
        timeout_seconds=5,
    )

    assert extraction.title == "Fixture"
    assert "Hello world" in extraction.text


@pytest.mark.integration
def test_real_public_atom_source_end_to_end() -> None:
    source = _register(
        kind=SourceKind.ATOM,
        base_url="https://github.com/fastapi/fastapi/releases.atom",
        vertical_keys=[],
    )
    client = httpx.Client(follow_redirects=True)
    try:
        result = ScoutAgent(get_session_factory()).ingest(
            source.id,
            RssAtomAdapter(client),
            force=True,
        )
    finally:
        client.close()

    assert result.status == "SUCCEEDED"
    assert result.created_count >= 1
    with get_session_factory()() as session:
        count = session.scalar(
            select(func.count())
            .select_from(SourceItem)
            .where(SourceItem.source_id == source.id)
        )
        assert count is not None
        assert count >= 1
