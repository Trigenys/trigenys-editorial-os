import asyncio
import importlib
from collections.abc import Callable
from typing import Any

from editorial_os_api.domain.enums import SourceFailureKind
from editorial_os_api.scout.contracts import PageExtraction
from editorial_os_api.scout.errors import SourceAdapterError


class Crawl4AIExtractionAdapter:
    """Optional Crawl4AI 0.9.x adapter loaded only when the crawl extra is installed."""

    name = "crawl4ai"

    def __init__(self, crawler_factory: Callable[[], Any] | None = None) -> None:
        self._crawler_factory = crawler_factory or self._default_factory

    def extract(self, url: str, *, timeout_seconds: float) -> PageExtraction:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "Crawl4AIExtractionAdapter.extract() must run in a worker thread "
                "when an asyncio event loop is already active."
            )

        try:
            return asyncio.run(
                asyncio.wait_for(
                    self._extract_async(url),
                    timeout=timeout_seconds,
                )
            )
        except TimeoutError as exc:
            raise SourceAdapterError(
                f"Crawl4AI extraction timed out for {url}.",
                kind=SourceFailureKind.TIMEOUT,
                retryable=True,
            ) from exc

    async def _extract_async(self, url: str) -> PageExtraction:
        crawler = self._crawler_factory()
        try:
            async with crawler as active:
                result = await active.arun(url=url)
        except Exception as exc:
            raise SourceAdapterError(
                f"Crawl4AI extraction failed for {url}: {type(exc).__name__}.",
                kind=SourceFailureKind.EXTRACTION,
                retryable=True,
            ) from exc

        success = getattr(result, "success", True)
        if success is False:
            error_message = getattr(result, "error_message", None)
            raise SourceAdapterError(
                f"Crawl4AI returned an unsuccessful result: {error_message or 'unknown error'}.",
                kind=SourceFailureKind.EXTRACTION,
                retryable=True,
            )

        markdown = getattr(result, "markdown", None)
        if not isinstance(markdown, str):
            raw_markdown = getattr(markdown, "raw_markdown", None)
            markdown = raw_markdown if isinstance(raw_markdown, str) else ""

        html = getattr(result, "html", None)
        final_url = getattr(result, "url", url)
        if not isinstance(final_url, str):
            final_url = url

        metadata_raw = getattr(result, "metadata", None)
        metadata: dict[str, object] = (
            dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
        )
        title = metadata.get("title")
        return PageExtraction(
            requested_url=url,
            final_url=final_url,
            title=title if isinstance(title, str) else None,
            text=markdown,
            raw_payload=html if isinstance(html, str) else None,
            http_status=None,
            content_type="text/html",
            metadata={
                **metadata,
                "extractor": self.name,
            },
        )

    @staticmethod
    def _default_factory() -> Any:
        try:
            module = importlib.import_module("crawl4ai")
        except ImportError as exc:
            raise RuntimeError(
                "Crawl4AI is optional. Install the backend with the 'crawl' extra."
            ) from exc

        crawler_class = getattr(module, "AsyncWebCrawler", None)
        if crawler_class is None:
            raise RuntimeError("Installed Crawl4AI has no AsyncWebCrawler.")
        return crawler_class()
