"""Replaceable Scout source adapters."""

from editorial_os_api.scout.adapters.feed import RssAtomAdapter
from editorial_os_api.scout.adapters.manual import HttpPageExtractor, ManualUrlAdapter
from editorial_os_api.scout.adapters.rsshub import RSSHubAdapter

__all__ = [
    "HttpPageExtractor",
    "ManualUrlAdapter",
    "RSSHubAdapter",
    "RssAtomAdapter",
]
