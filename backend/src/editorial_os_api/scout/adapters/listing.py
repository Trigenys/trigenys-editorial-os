from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from editorial_os_api.domain.enums import SourceFailureKind
from editorial_os_api.scout.contracts import RawFetchBatch, RawSourceItem, SourceSnapshot
from editorial_os_api.scout.errors import SourceAdapterError


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        self._href = values.get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            value = " ".join(data.split())
            if value:
                self._text.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        text = " ".join(self._text).strip()
        if text:
            self.links.append((self._href, text))
        self._href = None
        self._text = []


class ListingPageAdapter:
    """Discover article URLs from a publisher listing/home page.

    This adapter deliberately stores only link metadata. Full article text is fetched later
    by the research/verification path for the small set of promoted candidates.
    """

    name = "listing-page"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        max_items: int = 50,
        min_title_length: int = 24,
    ) -> None:
        self._client = client
        self._max_items = max_items
        self._min_title_length = min_title_length

    def requested_url(self, source: SourceSnapshot) -> str:
        if not source.base_url:
            raise SourceAdapterError(
                "Listing-page source requires base_url.",
                kind=SourceFailureKind.CONFIGURATION,
                retryable=False,
            )
        return source.base_url

    def fetch(self, source: SourceSnapshot) -> RawFetchBatch:
        if not source.base_url:
            raise SourceAdapterError(
                "Listing-page source requires base_url.",
                kind=SourceFailureKind.CONFIGURATION,
                retryable=False,
            )

        owned_client = self._client is None
        client = self._client or httpx.Client(
            follow_redirects=True,
            headers={"User-Agent": source.fetch_policy.user_agent},
        )
        try:
            try:
                response = client.get(
                    source.base_url,
                    timeout=source.fetch_policy.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                raise SourceAdapterError(
                    f"Listing request timed out for {source.base_url}.",
                    kind=SourceFailureKind.TIMEOUT,
                    retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise SourceAdapterError(
                    f"Listing request failed for {source.base_url}: {type(exc).__name__}.",
                    kind=SourceFailureKind.HTTP_RETRYABLE,
                    retryable=True,
                ) from exc

            if response.status_code == 429 or response.status_code >= 500:
                raise SourceAdapterError(
                    f"Listing returned retryable HTTP {response.status_code}.",
                    kind=SourceFailureKind.HTTP_RETRYABLE,
                    retryable=True,
                    http_status=response.status_code,
                )
            if response.status_code >= 400:
                raise SourceAdapterError(
                    f"Listing returned terminal HTTP {response.status_code}.",
                    kind=SourceFailureKind.HTTP_TERMINAL,
                    retryable=False,
                    http_status=response.status_code,
                )

            items = self.parse(
                source,
                final_url=str(response.url),
                payload=response.text,
            )
            return RawFetchBatch(
                adapter=self.name,
                requested_url=str(response.url),
                raw_payload=response.text,
                http_status=response.status_code,
                content_type=response.headers.get("content-type"),
                items=items,
                metadata={"entry_count": len(items)},
            )
        finally:
            if owned_client:
                client.close()

    def parse(
        self,
        source: SourceSnapshot,
        *,
        final_url: str,
        payload: str,
    ) -> list[RawSourceItem]:
        collector = _LinkCollector()
        collector.feed(payload)

        origin = urlparse(final_url)
        seen: set[str] = set()
        items: list[RawSourceItem] = []
        for href, title in collector.links:
            normalized_title = " ".join(title.split()).strip()
            if len(normalized_title) < self._min_title_length:
                continue

            absolute = urljoin(final_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != origin.netloc:
                continue
            if self._excluded_path(parsed.path):
                continue

            canonical = parsed._replace(fragment="", query="").geturl()
            if canonical in seen:
                continue
            seen.add(canonical)
            items.append(
                RawSourceItem(
                    external_id=canonical,
                    url=canonical,
                    title=normalized_title,
                    body=None,
                    summary=None,
                    locale=source.locale,
                    payload={"discovery_transport": self.name},
                )
            )
            if len(items) >= self._max_items:
                break

        if not items:
            raise SourceAdapterError(
                "Listing page did not expose any article-like links.",
                kind=SourceFailureKind.PARSE,
                retryable=False,
            )
        return items

    @staticmethod
    def _excluded_path(path: str) -> bool:
        value = path.lower().rstrip("/")
        if value in {"", "/"}:
            return True
        excluded = (
            "/category/",
            "/tag/",
            "/author/",
            "/page/",
            "/contact",
            "/about",
            "/qui-sommes",
            "/pricing",
            "/offers",
            "/catalog",
            "/member/",
            "/legal/",
            "/feed",
            "/wp-",
        )
        return any(token in value for token in excluded)
