"""Source registry and deterministic Scout ingestion."""

from editorial_os_api.scout.contracts import (
    FetchPolicy,
    NormalizedSourceItem,
    RawFetchBatch,
    RawSourceItem,
    SourceSnapshot,
)
from editorial_os_api.scout.errors import SourceAdapterError
from editorial_os_api.scout.registry import SourceRegistry
from editorial_os_api.scout.service import ScoutAgent

__all__ = [
    "FetchPolicy",
    "NormalizedSourceItem",
    "RawFetchBatch",
    "RawSourceItem",
    "ScoutAgent",
    "SourceAdapterError",
    "SourceRegistry",
    "SourceSnapshot",
]
