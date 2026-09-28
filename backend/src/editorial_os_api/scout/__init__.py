"""Source registry and deterministic Scout ingestion."""

from editorial_os_api.scout.contracts import (
    FetchPolicy,
    NormalizedSourceItem,
    RawFetchBatch,
    RawSourceItem,
    ScoutIngestResult,
    SourceRegistration,
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
    "ScoutIngestResult",
    "SourceAdapterError",
    "SourceRegistration",
    "SourceRegistry",
    "SourceSnapshot",
]
