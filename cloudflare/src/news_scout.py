from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from workers import fetch as worker_fetch

from editorial_os_api.config import Settings
from editorial_os_api.domain.enums import (
    SourceFailureKind,
    SourceHealthStatus,
    SourceKind,
)
from editorial_os_api.persistence.models import Source
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.scout import ScoutAgent
from editorial_os_api.scout.adapters.feed import RssAtomAdapter
from editorial_os_api.scout.adapters.listing import ListingPageAdapter
from editorial_os_api.scout.adapters.sitemap import NewsSitemapAdapter
from editorial_os_api.scout.contracts import RawFetchBatch, SourceSnapshot
from editorial_os_api.scout.errors import SourceAdapterError
from editorial_os_api.scout.news_registry import NEWS_REGISTRY_ID, seed_news_sources
from editorial_os_api.scout.registry import SourceRegistry

CANARY_SOURCE_KEYS = (
    "digital-business-africa",
    "ecomatin",
    "techcabal",
    "reuters",
    "bleeping-computer",
)


def _due(source: SourceSnapshot, *, force: bool, now: datetime) -> tuple[bool, str | None]:
    if not source.enabled:
        return False, "disabled"
    if source.health_status is SourceHealthStatus.PAUSED and not force:
        return False, "paused"
    if source.next_fetch_at is not None and source.next_fetch_at > now and not force:
        return False, "backoff"
    return True, None


async def _fetch_text(
    url: str,
    source: SourceSnapshot,
) -> tuple[str, str, int, str | None]:
    try:
        response = await worker_fetch(
            url,
            headers={"User-Agent": source.fetch_policy.user_agent},
        )
    except Exception as exc:
        raise SourceAdapterError(
            f"Worker fetch failed for {url}: {type(exc).__name__}.",
            kind=SourceFailureKind.HTTP_RETRYABLE,
            retryable=True,
        ) from exc

    status = int(response.status)
    if status == 429 or status >= 500:
        raise SourceAdapterError(
            f"Source returned retryable HTTP {status}.",
            kind=SourceFailureKind.HTTP_RETRYABLE,
            retryable=True,
            http_status=status,
        )
    if status >= 400:
        raise SourceAdapterError(
            f"Source returned terminal HTTP {status}.",
            kind=SourceFailureKind.HTTP_TERMINAL,
            retryable=False,
            http_status=status,
        )

    payload = await response.text()
    final_url = str(getattr(response, "url", url))
    content_type = response.headers.get("content-type")
    return payload, final_url, status, content_type


async def _feed_batch(source: SourceSnapshot) -> RawFetchBatch:
    payload, final_url, status, content_type = await _fetch_text(
        source.base_url or "",
        source,
    )
    return RssAtomAdapter().parse(
        source,
        url=final_url,
        payload=payload,
        http_status=status,
        content_type=content_type,
    )


async def _listing_batch(source: SourceSnapshot) -> RawFetchBatch:
    payload, final_url, status, content_type = await _fetch_text(
        source.base_url or "",
        source,
    )
    items = ListingPageAdapter().parse(
        source,
        final_url=final_url,
        payload=payload,
    )
    return RawFetchBatch(
        adapter="listing-page",
        requested_url=final_url,
        raw_payload=payload,
        http_status=status,
        content_type=content_type,
        items=items,
        metadata={"entry_count": len(items)},
    )


async def _sitemap_batch(source: SourceSnapshot) -> RawFetchBatch:
    adapter = NewsSitemapAdapter()
    payload, final_url, status, content_type = await _fetch_text(
        source.base_url or "",
        source,
    )
    root = adapter._parse_xml(payload)

    if adapter._local_name(root.tag) != "sitemapindex":
        items = adapter._url_items(root, source.locale)[:60]
        return RawFetchBatch(
            adapter=adapter.name,
            requested_url=final_url,
            raw_payload=payload,
            http_status=status,
            content_type=content_type,
            cursor=adapter._cursor(items),
            items=items,
            metadata={"entry_count": len(items), "child_sitemaps": 0},
        )

    child_urls = adapter._child_sitemaps(root)[:3]
    raw_parts = [payload]
    items = []
    for child_url in child_urls:
        child_payload, _, _, _ = await _fetch_text(child_url, source)
        raw_parts.append(child_payload)
        child_root = adapter._parse_xml(child_payload)
        items.extend(adapter._url_items(child_root, source.locale))
        if len(items) >= 60:
            break

    items = items[:60]
    return RawFetchBatch(
        adapter=adapter.name,
        requested_url=final_url,
        raw_payload="\n".join(raw_parts),
        http_status=status,
        content_type=content_type,
        cursor=adapter._cursor(items),
        items=items,
        metadata={
            "entry_count": len(items),
            "child_sitemaps": len(child_urls),
        },
    )


async def _batch_for(source: SourceSnapshot) -> RawFetchBatch:
    mode = str(source.config.get("collection_mode") or "")
    if source.kind in {SourceKind.RSS, SourceKind.ATOM}:
        return await _feed_batch(source)
    if mode == "listing-page":
        return await _listing_batch(source)
    if mode == "news-sitemap":
        return await _sitemap_batch(source)
    raise SourceAdapterError(
        f"No Worker transport configured for {source.name}.",
        kind=SourceFailureKind.CONFIGURATION,
        retryable=False,
    )


def _source_rows(
    session_factory: sessionmaker[Session],
) -> dict[str, Source]:
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(Source).where(
                    Source.config["registry_id"].astext == NEWS_REGISTRY_ID,
                    Source.config["source_key"].astext.in_(CANARY_SOURCE_KEYS),
                )
            )
        )
    return {str(row.config["source_key"]): row for row in rows}


async def run_news_scout_canary(
    settings: Settings,
    *,
    force: bool = False,
) -> dict[str, Any]:
    session_factory = get_session_factory(settings)
    seed_news_sources(session_factory)

    rows = _source_rows(session_factory)
    missing = sorted(set(CANARY_SOURCE_KEYS) - set(rows))
    if missing:
        raise RuntimeError(f"Missing News Scout sources: {', '.join(missing)}")

    registry = SourceRegistry(session_factory)
    scout = ScoutAgent(session_factory)
    now = datetime.now(UTC)
    results: dict[str, Any] = {}

    for key in CANARY_SOURCE_KEYS:
        row = rows[key]
        snapshot = registry.get(row.id)
        eligible, skipped_reason = _due(snapshot, force=force, now=now)
        if not eligible:
            results[key] = {
                "source_id": str(snapshot.id),
                "status": "SKIPPED",
                "skipped_reason": skipped_reason,
            }
            continue

        try:
            batch = await _batch_for(snapshot)
            result = scout.persist_batch(
                snapshot.id,
                source_snapshot=snapshot,
                batch=batch,
                requested_url=batch.requested_url,
                observed_at=now,
            )
        except SourceAdapterError as exc:
            result = scout.record_failure(
                snapshot.id,
                adapter_name=str(snapshot.config.get("collection_mode") or snapshot.kind.value),
                requested_url=snapshot.base_url or "",
                error=exc,
                observed_at=now,
            )
        except Exception as exc:
            wrapped = SourceAdapterError(
                f"Unexpected News Scout failure: {type(exc).__name__}.",
                kind=SourceFailureKind.UNKNOWN,
                retryable=True,
            )
            result = scout.record_failure(
                snapshot.id,
                adapter_name=str(snapshot.config.get("collection_mode") or snapshot.kind.value),
                requested_url=snapshot.base_url or "",
                error=wrapped,
                observed_at=now,
            )

        results[key] = result.model_dump(mode="json")

    return {
        "registry": NEWS_REGISTRY_ID,
        "force": force,
        "ran_at": now.isoformat(),
        "results": results,
    }
