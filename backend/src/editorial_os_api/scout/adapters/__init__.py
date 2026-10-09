"""Replaceable Scout source adapters.

Imports stay lazy so a Worker that only needs the lightweight manual adapter does not
load optional RSS or Crawl4AI dependencies at module-import time.
"""

from typing import Any

__all__ = [
    "Crawl4AIExtractionAdapter",
    "HttpPageExtractor",
    "ManualUrlAdapter",
    "RSSHubAdapter",
    "RssAtomAdapter",
]


def __getattr__(name: str) -> Any:
    if name == "Crawl4AIExtractionAdapter":
        from editorial_os_api.scout.adapters.crawl4ai import Crawl4AIExtractionAdapter

        return Crawl4AIExtractionAdapter
    if name == "RssAtomAdapter":
        from editorial_os_api.scout.adapters.feed import RssAtomAdapter

        return RssAtomAdapter
    if name in {"HttpPageExtractor", "ManualUrlAdapter"}:
        from editorial_os_api.scout.adapters.manual import (
            HttpPageExtractor,
            ManualUrlAdapter,
        )

        return {
            "HttpPageExtractor": HttpPageExtractor,
            "ManualUrlAdapter": ManualUrlAdapter,
        }[name]
    if name == "RSSHubAdapter":
        from editorial_os_api.scout.adapters.rsshub import RSSHubAdapter

        return RSSHubAdapter
    raise AttributeError(name)
