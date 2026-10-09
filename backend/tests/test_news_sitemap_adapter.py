from datetime import UTC, datetime
from uuid import uuid4

import httpx

from editorial_os_api.domain.enums import EvidenceTier, SourceHealthStatus, SourceKind
from editorial_os_api.scout.adapters.sitemap import NewsSitemapAdapter
from editorial_os_api.scout.contracts import FetchPolicy, SourceSnapshot


def _source() -> SourceSnapshot:
    return SourceSnapshot(
        id=uuid4(),
        name="Reuters",
        kind=SourceKind.WEB,
        base_url="https://example.test/news-sitemap-index.xml",
        enabled=True,
        trust_tier=EvidenceTier.E4,
        default_evidence_tier=EvidenceTier.E4,
        locale="en",
        vertical_keys=["trigenys-insight"],
        fetch_policy=FetchPolicy(),
        retention_days=90,
        redact_raw_content=True,
        config={"collection_mode": "news-sitemap"},
        health_status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
    )


def test_news_sitemap_adapter_follows_latest_child_and_extracts_news_metadata() -> None:
    index = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap>
        <loc>https://example.test/news-old.xml</loc>
        <lastmod>2026-10-08T10:00:00Z</lastmod>
      </sitemap>
      <sitemap>
        <loc>https://example.test/news-new.xml</loc>
        <lastmod>2026-10-09T10:00:00Z</lastmod>
      </sitemap>
    </sitemapindex>
    """
    child = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
            xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      <url>
        <loc>https://example.test/article-one</loc>
        <news:news>
          <news:publication_date>2026-10-09T09:30:00Z</news:publication_date>
          <news:title>AI infrastructure story</news:title>
        </news:news>
      </url>
    </urlset>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("news-sitemap-index.xml"):
            return httpx.Response(200, text=index, headers={"content-type": "application/xml"})
        if str(request.url).endswith("news-new.xml"):
            return httpx.Response(
                200,
                text=child,
                headers={"content-type": "application/xml"},
            )
        return httpx.Response(
            200,
            text="<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9' />",
        )

    adapter = NewsSitemapAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_child_sitemaps=1,
    )
    batch = adapter.fetch(_source())

    assert batch.adapter == "news-sitemap"
    assert batch.metadata["child_sitemaps"] == 1
    assert len(batch.items) == 1
    assert batch.items[0].url == "https://example.test/article-one"
    assert batch.items[0].title == "AI infrastructure story"
    assert batch.items[0].published_at == datetime(2026, 10, 9, 9, 30, tzinfo=UTC)
