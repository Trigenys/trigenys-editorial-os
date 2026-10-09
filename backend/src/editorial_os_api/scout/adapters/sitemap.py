from __future__ import annotations

from datetime import UTC, datetime
from xml.etree import ElementTree

import httpx

from editorial_os_api.domain.enums import SourceFailureKind
from editorial_os_api.scout.contracts import RawFetchBatch, RawSourceItem, SourceSnapshot
from editorial_os_api.scout.errors import SourceAdapterError

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"


class NewsSitemapAdapter:
    name = "news-sitemap"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        max_child_sitemaps: int = 3,
        max_items: int = 60,
    ) -> None:
        self._client = client
        self._max_child_sitemaps = max_child_sitemaps
        self._max_items = max_items

    def requested_url(self, source: SourceSnapshot) -> str:
        if not source.base_url:
            raise SourceAdapterError(
                "News sitemap source requires base_url.",
                kind=SourceFailureKind.CONFIGURATION,
                retryable=False,
            )
        return source.base_url

    def fetch(self, source: SourceSnapshot) -> RawFetchBatch:
        if not source.base_url:
            raise SourceAdapterError(
                "News sitemap source requires base_url.",
                kind=SourceFailureKind.CONFIGURATION,
                retryable=False,
            )

        owned_client = self._client is None
        client = self._client or httpx.Client(
            follow_redirects=True,
            headers={"User-Agent": source.fetch_policy.user_agent},
        )
        try:
            index_response = self._get(client, source.base_url, source)
            root = self._parse_xml(index_response.text)

            if self._local_name(root.tag) == "sitemapindex":
                child_urls = self._child_sitemaps(root)[: self._max_child_sitemaps]
                items: list[RawSourceItem] = []
                raw_parts = [index_response.text]
                for child_url in child_urls:
                    child_response = self._get(client, child_url, source)
                    raw_parts.append(child_response.text)
                    child_root = self._parse_xml(child_response.text)
                    items.extend(self._url_items(child_root, source.locale))
                    if len(items) >= self._max_items:
                        break
                items = items[: self._max_items]
                return RawFetchBatch(
                    adapter=self.name,
                    requested_url=str(index_response.url),
                    raw_payload="\n".join(raw_parts),
                    http_status=index_response.status_code,
                    content_type=index_response.headers.get("content-type"),
                    cursor=self._cursor(items),
                    items=items,
                    metadata={
                        "entry_count": len(items),
                        "child_sitemaps": len(child_urls),
                    },
                )

            items = self._url_items(root, source.locale)[: self._max_items]
            return RawFetchBatch(
                adapter=self.name,
                requested_url=str(index_response.url),
                raw_payload=index_response.text,
                http_status=index_response.status_code,
                content_type=index_response.headers.get("content-type"),
                cursor=self._cursor(items),
                items=items,
                metadata={"entry_count": len(items), "child_sitemaps": 0},
            )
        finally:
            if owned_client:
                client.close()

    def _get(
        self,
        client: httpx.Client,
        url: str,
        source: SourceSnapshot,
    ) -> httpx.Response:
        try:
            response = client.get(url, timeout=source.fetch_policy.timeout_seconds)
        except httpx.TimeoutException as exc:
            raise SourceAdapterError(
                f"Sitemap request timed out for {url}.",
                kind=SourceFailureKind.TIMEOUT,
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise SourceAdapterError(
                f"Sitemap request failed for {url}: {type(exc).__name__}.",
                kind=SourceFailureKind.HTTP_RETRYABLE,
                retryable=True,
            ) from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise SourceAdapterError(
                f"Sitemap returned retryable HTTP {response.status_code}.",
                kind=SourceFailureKind.HTTP_RETRYABLE,
                retryable=True,
                http_status=response.status_code,
            )
        if response.status_code >= 400:
            raise SourceAdapterError(
                f"Sitemap returned terminal HTTP {response.status_code}.",
                kind=SourceFailureKind.HTTP_TERMINAL,
                retryable=False,
                http_status=response.status_code,
            )
        return response

    @staticmethod
    def _parse_xml(payload: str) -> ElementTree.Element:
        try:
            return ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise SourceAdapterError(
                "News sitemap could not be parsed.",
                kind=SourceFailureKind.PARSE,
                retryable=False,
            ) from exc

    def _child_sitemaps(self, root: ElementTree.Element) -> list[str]:
        rows: list[tuple[datetime, str]] = []
        for node in root.findall(f"{{{_SITEMAP_NS}}}sitemap"):
            loc = node.findtext(f"{{{_SITEMAP_NS}}}loc")
            if not loc:
                continue
            lastmod = self._datetime(node.findtext(f"{{{_SITEMAP_NS}}}lastmod"))
            rows.append((lastmod or datetime.min.replace(tzinfo=UTC), loc.strip()))
        rows.sort(key=lambda row: row[0], reverse=True)
        return [loc for _, loc in rows]

    def _url_items(
        self,
        root: ElementTree.Element,
        locale: str | None,
    ) -> list[RawSourceItem]:
        items: list[RawSourceItem] = []
        for node in root.findall(f"{{{_SITEMAP_NS}}}url"):
            loc = node.findtext(f"{{{_SITEMAP_NS}}}loc")
            if not loc:
                continue
            title = node.findtext(f".//{{{_NEWS_NS}}}title")
            publication_date = node.findtext(f".//{{{_NEWS_NS}}}publication_date")
            lastmod = node.findtext(f"{{{_SITEMAP_NS}}}lastmod")
            published_at = self._datetime(publication_date) or self._datetime(lastmod)
            items.append(
                RawSourceItem(
                    external_id=loc.strip(),
                    url=loc.strip(),
                    title=title.strip() if title else None,
                    body=None,
                    summary=None,
                    published_at=published_at,
                    locale=locale,
                    payload={"discovery_transport": "news-sitemap"},
                )
            )
        items.sort(
            key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return items

    @staticmethod
    def _cursor(items: list[RawSourceItem]) -> str | None:
        dates = [item.published_at for item in items if item.published_at is not None]
        return max(dates).isoformat() if dates else None

    @staticmethod
    def _datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        candidate = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
