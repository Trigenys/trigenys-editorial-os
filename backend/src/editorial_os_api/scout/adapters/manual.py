from html.parser import HTMLParser

import httpx

from editorial_os_api.domain.enums import SourceFailureKind
from editorial_os_api.scout.contracts import (
    PageExtraction,
    PageExtractor,
    RawFetchBatch,
    RawSourceItem,
    SourceSnapshot,
)
from editorial_os_api.scout.errors import SourceAdapterError


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._in_title = False
        self.title: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value:
            return
        self._pieces.append(value)
        if self._in_title:
            self.title = f"{self.title or ''} {value}".strip()

    @property
    def text(self) -> str:
        return " ".join(self._pieces)


class HttpPageExtractor:
    name = "http-page"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def extract(self, url: str, *, timeout_seconds: float) -> PageExtraction:
        owned_client = self._client is None
        client = self._client or httpx.Client(follow_redirects=True)
        try:
            try:
                response = client.get(url, timeout=timeout_seconds)
            except httpx.TimeoutException as exc:
                raise SourceAdapterError(
                    f"Page request timed out for {url}.",
                    kind=SourceFailureKind.TIMEOUT,
                    retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise SourceAdapterError(
                    f"Page request failed for {url}: {type(exc).__name__}.",
                    kind=SourceFailureKind.HTTP_RETRYABLE,
                    retryable=True,
                ) from exc

            if response.status_code == 429 or response.status_code >= 500:
                raise SourceAdapterError(
                    f"Page returned retryable HTTP {response.status_code}.",
                    kind=SourceFailureKind.HTTP_RETRYABLE,
                    retryable=True,
                    http_status=response.status_code,
                )
            if response.status_code >= 400:
                raise SourceAdapterError(
                    f"Page returned terminal HTTP {response.status_code}.",
                    kind=SourceFailureKind.HTTP_TERMINAL,
                    retryable=False,
                    http_status=response.status_code,
                )

            parser = _TextExtractor()
            parser.feed(response.text)
            return PageExtraction(
                requested_url=url,
                final_url=str(response.url),
                title=parser.title,
                text=parser.text,
                raw_payload=response.text,
                http_status=response.status_code,
                content_type=response.headers.get("content-type"),
                metadata={"extractor": self.name},
            )
        finally:
            if owned_client:
                client.close()


class ManualUrlAdapter:
    name = "manual-url"

    def __init__(
        self,
        url: str,
        extractor: PageExtractor,
        *,
        title: str | None = None,
        locale: str | None = None,
    ) -> None:
        self._url = url
        self._extractor = extractor
        self._title = title
        self._locale = locale

    def fetch(self, source: SourceSnapshot) -> RawFetchBatch:
        extraction = self._extractor.extract(
            self._url,
            timeout_seconds=source.fetch_policy.timeout_seconds,
        )
        return RawFetchBatch(
            adapter=self.name,
            requested_url=extraction.requested_url,
            raw_payload=extraction.raw_payload,
            http_status=extraction.http_status,
            content_type=extraction.content_type,
            items=[
                RawSourceItem(
                    external_id=None,
                    url=extraction.final_url,
                    title=self._title or extraction.title,
                    body=extraction.text,
                    locale=self._locale or source.locale,
                    payload=extraction.metadata,
                )
            ],
            metadata={"extractor": extraction.metadata.get("extractor", "unknown")},
        )
