from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from editorial_os_api.domain.enums import GateOutcome, WorkflowStatus


class OperatorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GateArtifact(OperatorModel):
    artifact_type: str
    artifact_id: UUID
    artifact_version: int


class OperatorRunSummary(OperatorModel):
    id: UUID
    vertical_key: str
    status: WorkflowStatus
    risk_class: str
    confidence_class: str
    state_version: int
    topic_title: str | None = None
    topic_decision: str | None = None
    topic_urgency: str | None = None
    pending_gate: str | None = None
    created_at: datetime
    updated_at: datetime


class OperatorClaim(OperatorModel):
    id: UUID
    statement: str
    material: bool
    confidence_class: str
    risk_class: str
    support_status: str
    stale: bool
    contested: bool


class OperatorEvidence(OperatorModel):
    id: UUID
    url: str
    excerpt: str | None = None
    tier: str
    source_role: str
    stale: bool
    observed_at: datetime


class OperatorDraft(OperatorModel):
    id: UUID
    version: int
    locale: str
    title: str
    deck: str | None = None
    body: str
    unsupported_factual_claims: list[str]


class OperatorAsset(OperatorModel):
    id: UUID
    version: int
    slot: str
    kind: str
    uri: str | None = None
    filename: str | None = None
    rights_status: str
    alt_text: str | None = None
    caption: str | None = None


class OperatorGateDecision(OperatorModel):
    id: UUID
    gate: str
    outcome: str
    artifact_type: str
    artifact_id: UUID
    artifact_version: int
    actor_id: str
    reason: str | None = None
    decided_at: datetime


class OperatorTimelineEvent(OperatorModel):
    id: UUID
    action_key: str
    action_type: str
    actor_kind: str
    actor_id: str
    from_status: str
    to_status: str
    from_state_version: int
    to_state_version: int
    created_at: datetime


class OperatorUsageSummary(OperatorModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0")
    average_latency_ms: float | None = None


class OperatorPublication(OperatorModel):
    id: UUID
    provider: str
    target: str
    status: str
    external_url: str | None = None
    scheduled_at: datetime | None = None
    published_at: datetime | None = None


class OperatorDistribution(OperatorModel):
    id: UUID
    provider: str
    channel: str
    status: str
    external_url: str | None = None
    created_at: datetime
    updated_at: datetime


class OperatorRunDetail(OperatorModel):
    run: OperatorRunSummary
    gate_artifact: GateArtifact | None = None
    claims: list[OperatorClaim] = Field(default_factory=list)
    evidence: list[OperatorEvidence] = Field(default_factory=list)
    draft: OperatorDraft | None = None
    assets: list[OperatorAsset] = Field(default_factory=list)
    gates: list[OperatorGateDecision] = Field(default_factory=list)
    timeline: list[OperatorTimelineEvent] = Field(default_factory=list)
    usage: OperatorUsageSummary = Field(default_factory=OperatorUsageSummary)
    publication: OperatorPublication | None = None
    distributions: list[OperatorDistribution] = Field(default_factory=list)
    recovery_action: Literal["RETRY", "RESUME"] | None = None


class GateActionRequest(OperatorModel):
    outcome: GateOutcome
    actor_id: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=1000)
    details: dict[str, object] = Field(default_factory=dict)


class RecoveryActionRequest(OperatorModel):
    actor_id: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=1000)
