from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from editorial_os_api.domain.enums import (
    ClaimSupportStatus,
    ConfidenceClass,
    EvidenceStance,
    EvidenceTier,
    ResearchBriefStatus,
    RiskClass,
)
from editorial_os_api.research_verification.contracts import (
    ClaimEvaluation,
    ClaimSeed,
    VerificationPolicy,
)

_CONFIDENCE_RANK = {
    ConfidenceClass.C0: 0,
    ConfidenceClass.C1: 1,
    ConfidenceClass.C2: 2,
    ConfidenceClass.C3: 3,
    ConfidenceClass.C4: 4,
}

_EVIDENCE_RANK = {
    EvidenceTier.E0: 0,
    EvidenceTier.E1: 1,
    EvidenceTier.E2: 2,
    EvidenceTier.E3: 3,
    EvidenceTier.E4: 4,
}

_RISK_RANK = {
    RiskClass.R0: 0,
    RiskClass.R1: 1,
    RiskClass.R2: 2,
    RiskClass.R3: 3,
}


@dataclass(frozen=True)
class LedgerEvidence:
    source_id: UUID
    tier: EvidenceTier
    stance: EvidenceStance
    stale: bool


def confidence_at_least(
    actual: ConfidenceClass,
    required: ConfidenceClass,
) -> bool:
    return _CONFIDENCE_RANK[actual] >= _CONFIDENCE_RANK[required]


def max_risk(values: list[RiskClass]) -> RiskClass:
    return max(values, key=lambda item: _RISK_RANK[item])


def evaluate_claim(
    claim: ClaimSeed,
    evidence: list[LedgerEvidence],
) -> ClaimEvaluation:
    supports = [item for item in evidence if item.stance is EvidenceStance.SUPPORTS]
    refutes = [item for item in evidence if item.stance is EvidenceStance.REFUTES]
    usable = [*supports, *refutes]

    if not supports:
        return ClaimEvaluation(
            claim_key=claim.claim_key,
            confidence_class=ConfidenceClass.C0,
            confidence_reason_codes=["NO_SUPPORTING_EVIDENCE"],
            support_status=ClaimSupportStatus.UNSUPPORTED,
            stale=False,
            contested=bool(refutes),
            supporting_source_count=0,
            evidence_count=len(usable),
        )

    credible_support = [
        item for item in supports if _EVIDENCE_RANK[item.tier] >= _EVIDENCE_RANK[EvidenceTier.E2]
    ]
    credible_refute = [
        item for item in refutes if _EVIDENCE_RANK[item.tier] >= _EVIDENCE_RANK[EvidenceTier.E2]
    ]
    contested = bool(credible_support and credible_refute)
    stale = all(item.stale for item in supports)
    supporting_sources = {item.source_id for item in supports}

    if contested:
        confidence = ConfidenceClass.C1
        status = ClaimSupportStatus.CONTESTED
        reasons = ["MATERIAL_CONTRADICTION"]
    elif stale:
        confidence = ConfidenceClass.C1
        status = ClaimSupportStatus.STALE
        reasons = ["ALL_SUPPORTING_EVIDENCE_STALE"]
    else:
        highest = max((_EVIDENCE_RANK[item.tier] for item in supports), default=0)
        e2_or_better_sources = {
            item.source_id
            for item in supports
            if _EVIDENCE_RANK[item.tier] >= _EVIDENCE_RANK[EvidenceTier.E2]
        }
        has_primary = any(
            _EVIDENCE_RANK[item.tier] >= _EVIDENCE_RANK[EvidenceTier.E3]
            for item in supports
        )
        has_e4 = any(item.tier is EvidenceTier.E4 for item in supports)

        if has_e4 or (has_primary and len(e2_or_better_sources) >= 2):
            confidence = ConfidenceClass.C4
            reasons = ["PRIMARY_PLUS_INDEPENDENT_CORROBORATION"]
        elif has_primary:
            confidence = ConfidenceClass.C3
            reasons = ["PRIMARY_EVIDENCE"]
        elif highest >= _EVIDENCE_RANK[EvidenceTier.E2] and len(e2_or_better_sources) >= 2:
            confidence = ConfidenceClass.C3
            reasons = ["MULTIPLE_CREDIBLE_SECONDARY_SOURCES"]
        elif highest >= _EVIDENCE_RANK[EvidenceTier.E2]:
            confidence = ConfidenceClass.C2
            reasons = ["CREDIBLE_SECONDARY_EVIDENCE"]
        else:
            confidence = ConfidenceClass.C1
            reasons = ["WEAK_SOURCE_ONLY"]
        status = ClaimSupportStatus.SUPPORTED

    return ClaimEvaluation(
        claim_key=claim.claim_key,
        confidence_class=confidence,
        confidence_reason_codes=reasons,
        support_status=status,
        stale=stale,
        contested=contested,
        supporting_source_count=len(supporting_sources),
        evidence_count=len(usable),
    )


def overall_confidence(evaluations: list[ClaimEvaluation]) -> ConfidenceClass:
    if not evaluations:
        return ConfidenceClass.C0
    return min(
        (item.confidence_class for item in evaluations),
        key=lambda item: _CONFIDENCE_RANK[item],
    )


def classify_research_status(
    *,
    evaluations: list[ClaimEvaluation],
    material_claim_keys: set[str],
    risk_class: RiskClass,
    policy: VerificationPolicy,
) -> tuple[ResearchBriefStatus, bool, list[str]]:
    material = [
        item for item in evaluations if item.claim_key in material_claim_keys
    ]
    reasons: list[str] = []

    if not material:
        return (
            ResearchBriefStatus.INSUFFICIENT,
            True,
            ["NO_MATERIAL_CLAIMS"],
        )

    unsupported = [
        item for item in material
        if item.support_status is ClaimSupportStatus.UNSUPPORTED
    ]
    if unsupported:
        reasons.append("MATERIAL_CLAIM_UNSUPPORTED")
        return ResearchBriefStatus.INSUFFICIENT, True, reasons

    confidence = overall_confidence(material)
    contested = any(item.contested for item in material)

    if risk_class is RiskClass.R3:
        reasons.append("R3_RESTRICTED")
    if risk_class is RiskClass.R2:
        reasons.append("SENSITIVE_RISK_REVIEW")
    if contested:
        reasons.append("MATERIAL_CONTRADICTION")
    if not confidence_at_least(confidence, policy.auto_verify_min_confidence):
        reasons.append("LOW_CONFIDENCE_REVIEW")
    if risk_class is RiskClass.R2 and not confidence_at_least(
        confidence,
        policy.sensitive_min_confidence,
    ):
        reasons.append("SENSITIVE_CONFIDENCE_BELOW_THRESHOLD")

    review_required = bool(reasons)
    if review_required:
        return ResearchBriefStatus.REVIEW_REQUIRED, True, reasons

    return ResearchBriefStatus.VERIFIED, False, ["RESEARCH_POLICY_SATISFIED"]
