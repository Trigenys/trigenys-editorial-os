"""Replaceable Scout source adapters."""

from editorial_os_api.scout.adapters.crawl4ai import Crawl4AIExtractionAdapter
from editorial_os_api.scout.adapters.feed import RssAtomAdapter
from editorial_os_api.scout.adapters.manual import HttpPageExtractor, ManualUrlAdapter
from editorial_os_api.scout.adapters.rsshub import RSSHubAdapter

__all__ = [
    "Crawl4AIExtractionAdapter",
    "HttpPageExtractor",
    "ManualUrlAdapter",
    "RSSHubAdapter",
    "RssAtomAdapter",
]
