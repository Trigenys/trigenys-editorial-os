from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from editorial_os_api.domain.enums import (
    ConfidenceClass,
    QAFindingSeverity,
    QAOutcome,
    RiskClass,
)
from editorial_os_api.editorial_qa.contracts import QAFinding

_CONFIDENCE_RANK = {
    ConfidenceClass.C0: 0,
    ConfidenceClass.C1: 1,
    ConfidenceClass.C2: 2,
    ConfidenceClass.C3: 3,
    ConfidenceClass.C4: 4,
}


class EditorialQAPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="1", min_length=1, max_length=80)
    min_pass_confidence: ConfidenceClass = ConfidenceClass.C2
    high_risk_human_approval: list[RiskClass] = Field(
        default_factory=lambda: [RiskClass.R2, RiskClass.R3]
    )
    require_semantic_checks: bool = True
    block_unsupported_material_claims: bool = True
    revise_stale_material_claims: bool = True
    revise_contested_material_claims: bool = True
    block_restricted_assets: bool = True


def confidence_at_least(
    actual: ConfidenceClass,
    required: ConfidenceClass,
) -> bool:
    return _CONFIDENCE_RANK[actual] >= _CONFIDENCE_RANK[required]


def outcome_for_findings(findings: list[QAFinding]) -> QAOutcome:
    if any(item.severity is QAFindingSeverity.BLOCKER for item in findings):
        return QAOutcome.BLOCK
    if any(item.severity is QAFindingSeverity.ERROR for item in findings):
        return QAOutcome.REVISE
    return QAOutcome.PASS
