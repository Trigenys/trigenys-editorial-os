from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from editorial_os_api.domain.enums import (
    AssetKind,
    AuditActorKind,
    ClaimSupportStatus,
    ConfidenceClass,
    DistributionStatus,
    EvidenceTier,
    GateKind,
    GateOutcome,
    PublicationStatus,
    ResearchBriefStatus,
    RiskClass,
    SourceFetchStatus,
    SourceHealthStatus,
    SourceKind,
    SourceRole,
    TopicDecision,
    TopicUrgency,
    WorkflowStatus,
)


class Contract(BaseModel):
    """Versioned provider-agnostic boundary shared by agents and the API."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"] = "1"


class SourceContract(Contract):
    id: UUID
    name: str
    kind: SourceKind
    enabled: bool = True
    trust_tier: EvidenceTier = EvidenceTier.E1
    default_evidence_tier: EvidenceTier = EvidenceTier.E1
    locale: str | None = None
    vertical_keys: list[str] = Field(default_factory=list)
    fetch_policy: dict[str, Any] = Field(default_factory=dict)
    retention_days: int | None = None
    redact_raw_content: bool = False
    health_status: SourceHealthStatus = SourceHealthStatus.HEALTHY
    consecutive_failures: int = 0
    next_fetch_at: datetime | None = None
    cursor: str | None = None


class SourceFetchContract(Contract):
    id: UUID
    source_id: UUID
    adapter: str
    requested_url: str
    status: SourceFetchStatus
    failure_kind: str | None = None
    retryable: bool | None = None
    started_at: datetime
    completed_at: datetime
    http_status: int | None = None
    content_type: str | None = None
    raw_sha256: str | None = None


class SourceItemContract(Contract):
    id: UUID
    source_id: UUID
    source_fetch_id: UUID | None = None
    external_id: str | None = None
    identity_key: str
    canonical_url: str
    title: str | None = None
    content_hash: str
    locale: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    published_at: datetime | None = None
    observed_at: datetime
    retain_until: datetime | None = None
    redacted_at: datetime | None = None


class TopicCandidateContract(Contract):
    id: UUID
    workflow_run_id: UUID
    version: int = 1
    cluster_key: str = ""
    title: str
    proposed_angle: str
    proposed_format: str = "article"
    urgency: TopicUrgency = TopicUrgency.NORMAL
    decision: TopicDecision
    novelty_score: int = 0
    relevance_score: int = 0
    source_diversity_score: int = 0
    composite_score: int = 0
    risk_class: RiskClass
    confidence_class: ConfidenceClass
    reason_codes: list[str] = Field(default_factory=list)
    source_item_ids: list[UUID] = Field(default_factory=list)
    reason_details: dict[str, Any] = Field(default_factory=dict)


class EvidenceItemContract(Contract):
    id: UUID
    workflow_run_id: UUID
    source_item_id: UUID | None = None
    url: str
    excerpt: str | None = None
    tier: EvidenceTier
    source_role: SourceRole = SourceRole.SECONDARY
    stale: bool = False
    extraction_method: str = "legacy"
    metadata: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime
    published_at: datetime | None = None
    retain_until: datetime | None = None
    redacted_at: datetime | None = None


class ClaimContract(Contract):
    id: UUID
    workflow_run_id: UUID
    claim_key: str = ""
    statement: str
    material: bool = True
    confidence_class: ConfidenceClass
    confidence_reason_codes: list[str] = Field(default_factory=list)
    risk_class: RiskClass
    support_status: ClaimSupportStatus = ClaimSupportStatus.UNKNOWN
    evidence_ids: list[UUID] = Field(default_factory=list)
    stale: bool = False
    contested: bool = False


class ResearchBriefContract(Contract):
    id: UUID
    workflow_run_id: UUID
    topic_candidate_id: UUID
    version: int
    status: ResearchBriefStatus
    confidence_class: ConfidenceClass
    risk_class: RiskClass
    reason_codes: list[str] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    contradiction_claim_ids: list[UUID] = Field(default_factory=list)
    unsupported_claim_ids: list[UUID] = Field(default_factory=list)
    stale_claim_ids: list[UUID] = Field(default_factory=list)
    source_plan: list[dict[str, Any]] = Field(default_factory=list)
    budget_usage: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False


class EditorialBriefContract(Contract):
    id: UUID
    workflow_run_id: UUID
    version: int
    angle: str
    locale: str
    claim_ids: list[UUID] = Field(default_factory=list)


class DraftContract(Contract):
    id: UUID
    workflow_run_id: UUID
    editorial_brief_id: UUID
    research_brief_id: UUID | None = None
    revision_of_id: UUID | None = None
    version: int
    locale: str
    content_format: str = "article"
    vertical_pack_key: str = "legacy"
    vertical_pack_version: str = "legacy"
    title: str
    deck: str | None = None
    body: str
    sections: list[dict[str, Any]] = Field(default_factory=list)
    seo_metadata: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    internal_link_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    unsupported_factual_claims: list[str] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)
    unsupported_claim_ids: list[UUID] = Field(default_factory=list)


class AssetContract(Contract):
    id: UUID
    workflow_run_id: UUID
    version: int
    kind: AssetKind
    uri: str | None = None
    alt_text: str | None = None
    caption: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    owner_key: str


class GateDecisionContract(Contract):
    id: UUID
    workflow_run_id: UUID
    gate: GateKind
    outcome: GateOutcome
    artifact_type: str
    artifact_id: UUID
    artifact_version: int
    actor_id: str
    decided_at: datetime
    reason: str | None = None


class PublicationContract(Contract):
    id: UUID
    workflow_run_id: UUID
    draft_id: UUID
    provider: str
    target: str
    status: PublicationStatus
    owner_key: str
    idempotency_key: str
    external_id: str | None = None


class DistributionJobContract(Contract):
    id: UUID
    workflow_run_id: UUID
    publication_id: UUID
    provider: str
    channel: str
    status: DistributionStatus
    owner_key: str
    idempotency_key: str
    external_id: str | None = None


class PerformanceSnapshotContract(Contract):
    id: UUID
    workflow_run_id: UUID
    publication_id: UUID | None = None
    distribution_job_id: UUID | None = None
    captured_at: datetime
    metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)


class WorkflowRunContract(Contract):
    id: UUID
    vertical_key: str
    vertical_version: str
    status: WorkflowStatus
    risk_class: RiskClass
    confidence_class: ConfidenceClass
    policy_version: str
    idempotency_key: str
    state_version: int = 0
    resume_status: WorkflowStatus | None = None
    created_at: datetime
    updated_at: datetime


class AuditEventContract(Contract):
    id: UUID
    workflow_run_id: UUID | None = None
    actor_kind: AuditActorKind
    actor_id: str
    event_type: str
    entity_type: str
    entity_id: UUID | None = None
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
