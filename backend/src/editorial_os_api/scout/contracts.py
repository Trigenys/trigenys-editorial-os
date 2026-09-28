from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from editorial_os_api.domain.enums import EvidenceTier, SourceHealthStatus, SourceKind


class ScoutModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FetchPolicy(ScoutModel):
    interval_seconds: int = Field(default=900, ge=60, le=86_400)
    timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    max_backoff_seconds: int = Field(default=21_600, ge=60, le=604_800)
    max_failures_before_pause: int = Field(default=8, ge=1, le=100)
    user_agent: str = Field(
        default="TrigenysEditorialOS/0.1 (+https://github.com/Trigenys/trigenys-editorial-os)",
        min_length=1,
        max_length=255,
    )


class SourceRegistration(ScoutModel):
    name: str = Field(min_length=1, max_length=200)
    kind: SourceKind
    base_url: str | None = None
    enabled: bool = True
    trust_tier: EvidenceTier = EvidenceTier.E1
    default_evidence_tier: EvidenceTier = EvidenceTier.E1
    locale: str | None = Field(default=None, max_length=32)
    vertical_keys: list[str] = Field(default_factory=list)
    fetch_policy: FetchPolicy = Field(default_factory=FetchPolicy)
    retention_days: int | None = Field(default=None, ge=1)
    redact_raw_content: bool = False
    config: dict[str, object] = Field(default_factory=dict)


class SourceSnapshot(ScoutModel):
    id: UUID
    name: str
    kind: SourceKind
    base_url: str | None = None
    enabled: bool
    trust_tier: EvidenceTier
    default_evidence_tier: EvidenceTier
    locale: str | None = None
    vertical_keys: list[str] = Field(default_factory=list)
    fetch_policy: FetchPolicy = Field(default_factory=FetchPolicy)
    redact_raw_content: bool = False
    config: dict[str, object] = Field(default_factory=dict)
    health_status: SourceHealthStatus = SourceHealthStatus.HEALTHY
    consecutive_failures: int = 0
    next_fetch_at: datetime | None = None
    cursor: str | None = None


class RawSourceItem(ScoutModel):
    external_id: str | None = None
    url: str
    title: str | None = None
    body: str | None = None
    summary: str | None = None
    published_at: datetime | None = None
    locale: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class RawFetchBatch(ScoutModel):
    adapter: str
    requested_url: str
    raw_payload: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    cursor: str | None = None
    items: list[RawSourceItem] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class NormalizedSourceItem(ScoutModel):
    source_id: UUID
    source_fetch_id: UUID
    external_id: str | None = None
    identity_key: str
    canonical_url: str
    title: str | None = None
    content_hash: str
    locale: str | None = None
    extracted_payload: dict[str, object] = Field(default_factory=dict)
    provenance: dict[str, object] = Field(default_factory=dict)
    published_at: datetime | None = None
    observed_at: datetime


class ScoutIngestResult(ScoutModel):
    source_id: UUID
    fetch_id: UUID | None = None
    status: str
    created_count: int = 0
    updated_count: int = 0
    skipped_reason: str | None = None
    failure_kind: str | None = None
    retryable: bool | None = None


class PageExtraction(ScoutModel):
    requested_url: str
    final_url: str
    title: str | None = None
    text: str
    raw_payload: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SourceAdapter(Protocol):
    def fetch(self, source: SourceSnapshot) -> RawFetchBatch: ...


class PageExtractor(Protocol):
    def extract(self, url: str, *, timeout_seconds: float) -> PageExtraction: ...


class ManualUrlInput(ScoutModel):
    url: HttpUrl
    title: str | None = None
    locale: str | None = None
