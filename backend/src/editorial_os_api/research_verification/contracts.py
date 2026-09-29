from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from editorial_os_api.domain.enums import (
    ClaimSupportStatus,
    ConfidenceClass,
    EvidenceStance,
    EvidenceTier,
    ResearchBriefStatus,
    RiskClass,
    SourceRole,
)


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchBudget(ResearchModel):
    max_sources: int = Field(default=8, ge=1, le=100)
    max_claims: int = Field(default=12, ge=1, le=100)
    max_evidence_items: int = Field(default=40, ge=1, le=500)
    max_adapter_calls: int = Field(default=20, ge=1, le=500)


class VerificationPolicy(ResearchModel):
    version: str = Field(default="1", min_length=1, max_length=80)
    stale_after_hours: int = Field(default=72, ge=1, le=24 * 365)
    auto_verify_min_confidence: ConfidenceClass = ConfidenceClass.C2
    sensitive_min_confidence: ConfidenceClass = ConfidenceClass.C3
    early_stop_confidence: ConfidenceClass = ConfidenceClass.C3
    early_stop_independent_sources: int = Field(default=2, ge=1, le=10)


class ClaimSeed(ResearchModel):
    claim_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._:-]*$",
    )
    statement: str = Field(min_length=1, max_length=2000)
    material: bool = True
    risk_class: RiskClass = RiskClass.R0


class ClaimPlanOutput(ResearchModel):
    claims: list[ClaimSeed] = Field(min_length=1)

    @model_validator(mode="after")
    def claim_keys_must_be_unique(self) -> ClaimPlanOutput:
        keys = [claim.claim_key for claim in self.claims]
        if len(keys) != len(set(keys)):
            raise ValueError("claim_key values must be unique.")
        return self


class ResearchSourceDocument(ResearchModel):
    source_item_id: UUID
    source_id: UUID
    source_name: str
    url: str
    title: str
    text: str
    evidence_tier: EvidenceTier
    source_role: SourceRole
    content_hash: str
    published_at: datetime | None = None
    observed_at: datetime
    retain_until: datetime | None = None
    redacted_at: datetime | None = None


class EvidenceAssessment(ResearchModel):
    claim_key: str
    stance: EvidenceStance
    excerpt: str | None = Field(default=None, max_length=4000)
    reason_code: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def usable_evidence_requires_excerpt(self) -> EvidenceAssessment:
        if self.stance is not EvidenceStance.NO_EVIDENCE:
            if self.excerpt is None or not self.excerpt.strip():
                raise ValueError("Non-empty excerpt required for usable evidence.")
        return self


class SourceAssessmentOutput(ResearchModel):
    assessments: list[EvidenceAssessment] = Field(default_factory=list)


class ClaimEvaluation(ResearchModel):
    claim_key: str
    confidence_class: ConfidenceClass
    confidence_reason_codes: list[str]
    support_status: ClaimSupportStatus
    stale: bool
    contested: bool
    supporting_source_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)


class ResearchVerificationResult(ResearchModel):
    workflow_run_id: UUID
    research_brief_id: UUID
    research_brief_version: int
    status: ResearchBriefStatus
    confidence_class: ConfidenceClass
    risk_class: RiskClass
    review_required: bool
    claim_ids: list[UUID]
    evidence_ids: list[UUID]
    contradiction_claim_ids: list[UUID]
    unsupported_claim_ids: list[UUID]
    stale_claim_ids: list[UUID]
    reason_codes: list[str]
    workflow_status: str


class ResearchAdapter(Protocol):
    name: str

    def plan_claims(
        self,
        workflow_run_id: UUID,
        *,
        candidate_title: str,
        candidate_angle: str,
        sources: list[ResearchSourceDocument],
        max_claims: int,
        call_key: str,
    ) -> list[ClaimSeed]: ...

    def assess_source(
        self,
        workflow_run_id: UUID,
        *,
        source: ResearchSourceDocument,
        claims: list[ClaimSeed],
        call_key: str,
    ) -> SourceAssessmentOutput: ...
