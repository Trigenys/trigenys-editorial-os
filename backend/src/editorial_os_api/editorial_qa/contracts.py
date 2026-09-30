from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from editorial_os_api.domain.enums import (
    AssetKind,
    AssetOrigin,
    AssetRightsStatus,
    ClaimSupportStatus,
    ConfidenceClass,
    QAFindingSeverity,
    QAOutcome,
    RiskClass,
)
from editorial_os_api.vertical_packs import VerticalPack


class QAModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QAClaimContext(QAModel):
    id: UUID
    claim_key: str
    statement: str
    material: bool
    support_status: ClaimSupportStatus
    confidence_class: ConfidenceClass
    risk_class: RiskClass
    stale: bool = False
    contested: bool = False
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    refuting_evidence_ids: list[UUID] = Field(default_factory=list)


class QAEvidenceContext(QAModel):
    id: UUID
    url: str
    tier: str
    stale: bool = False


class QAAssetContext(QAModel):
    id: UUID
    version: int
    slot: str
    kind: AssetKind
    origin: AssetOrigin
    rights_status: AssetRightsStatus
    alt_text: str | None = None
    caption: str | None = None
    filename: str | None = None


class QADraftContext(QAModel):
    id: UUID
    version: int
    locale: str
    content_format: str
    title: str
    deck: str | None = None
    body: str
    sections: list[dict[str, object]] = Field(default_factory=list)
    unsupported_factual_claims: list[str] = Field(default_factory=list)


class SemanticQAFinding(QAModel):
    code: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Z0-9][A-Z0-9._-]*$",
    )
    severity: Literal["WARNING", "ERROR"]
    category: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)
    location: str | None = Field(default=None, max_length=300)
    claim_id: UUID | None = None
    asset_id: UUID | None = None


class SemanticQAOutput(QAModel):
    findings: list[SemanticQAFinding] = Field(default_factory=list)


class QAFinding(QAModel):
    code: str = Field(min_length=1, max_length=120)
    severity: QAFindingSeverity
    category: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)
    location: str | None = Field(default=None, max_length=300)
    claim_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    asset_id: UUID | None = None
    policy_rule: str | None = Field(default=None, max_length=160)
    metadata: dict[str, object] = Field(default_factory=dict)


class QASubjectSnapshot(QAModel):
    draft_id: UUID
    draft_version: int
    manifest_id: UUID
    manifest_version: int
    asset_ids: list[UUID] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class EditorialQAResult(QAModel):
    workflow_run_id: UUID
    review_id: UUID
    review_version: int
    outcome: QAOutcome
    confidence_class: ConfidenceClass
    risk_class: RiskClass
    human_approval_required: bool
    gate_b_ready: bool
    findings: list[QAFinding]
    reason_codes: list[str]
    subject_snapshot: QASubjectSnapshot
    workflow_status: str


class EditorialQAAdapter(Protocol):
    name: str

    def review(
        self,
        workflow_run_id: UUID,
        *,
        draft: QADraftContext,
        claims: list[QAClaimContext],
        assets: list[QAAssetContext],
        vertical_pack: VerticalPack,
        call_key: str,
    ) -> SemanticQAOutput: ...
