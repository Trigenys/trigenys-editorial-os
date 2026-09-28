import calendar
from datetime import UTC, datetime
from time import struct_time
from typing import Any, cast

import feedparser  # type: ignore[import-untyped]
import httpx

from editorial_os_api.domain.enums import SourceFailureKind
from editorial_os_api.scout.contracts import RawFetchBatch, RawSourceItem, SourceSnapshot
from editorial_os_api.scout.errors import SourceAdapterError


class RssAtomAdapter:
    name = "rss-atom"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def requested_url(self, source: SourceSnapshot) -> str:
        if not source.base_url:
            raise SourceAdapterError(
                "RSS/Atom source requires base_url.",
                kind=SourceFailureKind.CONFIGURATION,
                retryable=False,
            )
        return source.base_url

    def fetch(self, source: SourceSnapshot) -> RawFetchBatch:
        if not source.base_url:
            raise SourceAdapterError(
                "RSS/Atom source requires base_url.",
                kind=SourceFailureKind.CONFIGURATION,
                retryable=False,
            )
        return self.fetch_url(source, source.base_url)

    def fetch_url(self, source: SourceSnapshot, url: str) -> RawFetchBatch:
        owned_client = self._client is None
        client = self._client or httpx.Client(
            follow_redirects=True,
            headers={"User-Agent": source.fetch_policy.user_agent},
        )
        try:
            try:
                response = client.get(url, timeout=source.fetch_policy.timeout_seconds)
            except httpx.TimeoutException as exc:
                raise SourceAdapterError(
                    f"Feed request timed out for {url}.",
                    kind=SourceFailureKind.TIMEOUT,
                    retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise SourceAdapterError(
                    f"Feed request failed for {url}: {type(exc).__name__}.",
                    kind=SourceFailureKind.HTTP_RETRYABLE,
                    retryable=True,
                ) from exc

            if response.status_code == 429 or response.status_code >= 500:
                raise SourceAdapterError(
                    f"Feed returned retryable HTTP {response.status_code}.",
                    kind=SourceFailureKind.HTTP_RETRYABLE,
                    retryable=True,
                    http_status=response.status_code,
                )
            if response.status_code >= 400:
                raise SourceAdapterError(
                    f"Feed returned terminal HTTP {response.status_code}.",
                    kind=SourceFailureKind.HTTP_TERMINAL,
                    retryable=False,
                    http_status=response.status_code,
                )

            return self.parse(
                source,
                url=str(response.url),
                payload=response.text,
                http_status=response.status_code,
                content_type=response.headers.get("content-type"),
            )
        finally:
            if owned_client:
                client.close()

    def parse(
        self,
        source: SourceSnapshot,
        *,
        url: str,
        payload: str,
        http_status: int | None = None,
        content_type: str | None = None,
    ) -> RawFetchBatch:
        parsed: Any = feedparser.loads(payload)
        entries = cast(list[Any], getattr(parsed, "entries", []))
        if getattr(parsed, "bozo", False) and not entries:
            raise SourceAdapterError(
                "Feed could not be parsed.",
                kind=SourceFailureKind.PARSE,
                retryable=False,
            )

        items = [self._entry_to_item(entry, source.locale) for entry in entries]
        feed = getattr(parsed, "feed", {})
        cursor = self._string_value(feed, "updated") or self._string_value(feed, "published")
        return RawFetchBatch(
            adapter=self.name,
            requested_url=url,
            raw_payload=payload,
            http_status=http_status,
            content_type=content_type,
            cursor=cursor,
            items=items,
            metadata={
                "feed_title": self._string_value(feed, "title"),
                "entry_count": len(items),
            },
        )

    def _entry_to_item(self, entry: Any, locale: str | None) -> RawSourceItem:
        link = self._string_value(entry, "link")
        external_id = self._string_value(entry, "id") or self._string_value(entry, "guid")
        if not link:
            raise SourceAdapterError(
                "Feed entry has no canonical web link.",
                kind=SourceFailureKind.PARSE,
                retryable=False,
            )

        body = self._entry_body(entry)
        published = self._entry_datetime(entry)
        return RawSourceItem(
            external_id=external_id,
            url=link,
            title=self._string_value(entry, "title"),
            body=body,
            summary=self._string_value(entry, "summary"),
            published_at=published,
            locale=locale,
            payload={
                "author": self._string_value(entry, "author"),
            },
        )

    @staticmethod
    def _entry_body(entry: Any) -> str | None:
        content = getattr(entry, "content", None)
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                value = first.get("value")
                if isinstance(value, str):
                    return value
            value = getattr(first, "value", None)
            if isinstance(value, str):
                return value
        summary = getattr(entry, "summary", None)
        return summary if isinstance(summary, str) else None

    @staticmethod
    def _entry_datetime(entry: Any) -> datetime | None:
        for field in ("published_parsed", "updated_parsed"):
            value = getattr(entry, field, None)
            if isinstance(value, struct_time):
                return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)
        return None

    @staticmethod
    def _string_value(container: Any, key: str) -> str | None:
        if isinstance(container, dict):
            value = container.get(key)
        else:
            value = getattr(container, key, None)
        return value if isinstance(value, str) and value.strip() else None
