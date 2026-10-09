from uuid import uuid4

import httpx

from editorial_os_api.domain.enums import EvidenceTier, SourceHealthStatus, SourceKind
from editorial_os_api.scout.adapters.listing import ListingPageAdapter
from editorial_os_api.scout.contracts import FetchPolicy, SourceSnapshot


def _source() -> SourceSnapshot:
    return SourceSnapshot(
        id=uuid4(),
        name="Publisher",
        kind=SourceKind.WEB,
        base_url="https://example.test/",
        enabled=True,
        trust_tier=EvidenceTier.E3,
        default_evidence_tier=EvidenceTier.E3,
        locale="fr",
        vertical_keys=["trigenys-insight"],
        fetch_policy=FetchPolicy(),
        retention_days=90,
        redact_raw_content=True,
        config={"collection_mode": "listing-page"},
        health_status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
    )


def test_listing_adapter_keeps_article_like_links_and_deduplicates() -> None:
    html = """
    <html><body>
      <nav><a href="/category/tech">Technology category</a></nav>
      <article><a href="/article-one">A serious technology story from Cameroon</a></article>
      <article><a href="/article-one#comments">A serious technology story from Cameroon</a></article>
      <article><a href="https://example.test/article-two?utm_source=home">
        Another sufficiently descriptive business technology headline
      </a></article>
      <a href="https://social.example/elsewhere">A very long external headline that should be ignored</a>
    </body></html>
    """

    adapter = ListingPageAdapter(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    text=html,
                    headers={"content-type": "text/html"},
                )
            )
        )
    )
    batch = adapter.fetch(_source())

    assert batch.adapter == "listing-page"
    assert len(batch.items) == 2
    assert {item.url for item in batch.items} == {
        "https://example.test/article-one",
        "https://example.test/article-two",
    }
    assert all(item.body is None for item in batch.items)
