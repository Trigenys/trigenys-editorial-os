from __future__ import annotations

from uuid import UUID

from editorial_os_api.domain.enums import (
    AssetManifestStatus,
    AssetRightsStatus,
    ClaimSupportStatus,
    ConfidenceClass,
    QAFindingSeverity,
    RiskClass,
)
from editorial_os_api.editorial_qa.contracts import QAFinding
from editorial_os_api.editorial_qa.loading import QASubject
from editorial_os_api.editorial_qa.policy import (
    EditorialQAPolicy,
    confidence_at_least,
)


def deterministic_findings(
    subject: QASubject,
    policy: EditorialQAPolicy,
) -> list[QAFinding]:
    findings: list[QAFinding] = []

    for statement in subject.draft.unsupported_factual_claims:
        findings.append(
            _finding(
                "UNSUPPORTED_DRAFT_ASSERTION",
                QAFindingSeverity.BLOCKER,
                "factual_support",
                "Draft contains a factual assertion outside the verified claim ledger.",
                location="draft.body",
                rule="block_unsupported_material_claims",
                metadata={"statement": statement},
            )
        )

    if policy.block_restricted_risk and subject.risk_class is RiskClass.R3:
        findings.append(
            _finding(
                "R3_RESTRICTED",
                QAFindingSeverity.BLOCKER,
                "risk",
                "R3 content cannot pass QA until an authorized human resolves the block.",
                rule="block_restricted_risk",
            )
        )

    material = [claim for claim in subject.claims if claim.material]
    if not material:
        findings.append(
            _finding(
                "NO_MATERIAL_CLAIMS",
                QAFindingSeverity.BLOCKER,
                "factual_support",
                "No material claim is linked to the draft.",
                rule="material_claim_support_required",
            )
        )

    for claim in material:
        supporting = list(claim.supporting_evidence_ids)
        if not supporting:
            findings.append(
                _finding(
                    "MATERIAL_CLAIM_WITHOUT_SUPPORTING_EVIDENCE",
                    QAFindingSeverity.BLOCKER,
                    "factual_support",
                    "Material claim has no supporting evidence edge.",
                    claim_id=claim.id,
                    rule="material_claim_support_required",
                )
            )

        if claim.support_status in {
            ClaimSupportStatus.UNSUPPORTED,
            ClaimSupportStatus.UNKNOWN,
        }:
            severity = (
                QAFindingSeverity.BLOCKER
                if policy.block_unsupported_material_claims
                else QAFindingSeverity.ERROR
            )
            findings.append(
                _finding(
                    "MATERIAL_CLAIM_UNSUPPORTED",
                    severity,
                    "factual_support",
                    "Material claim is unsupported or has unknown support.",
                    claim_id=claim.id,
                    evidence_ids=supporting,
                    rule="block_unsupported_material_claims",
                )
            )

        if (
            policy.revise_contested_material_claims
            and (
                claim.contested
                or claim.support_status is ClaimSupportStatus.CONTESTED
            )
        ):
            findings.append(
                _finding(
                    "MATERIAL_CLAIM_CONTESTED",
                    _contradiction_severity(subject.risk_class),
                    "contradiction",
                    "Material claim has contradictory evidence and needs revision.",
                    claim_id=claim.id,
                    evidence_ids=[
                        *supporting,
                        *claim.refuting_evidence_ids,
                    ],
                    rule="revise_contested_material_claims",
                )
            )

        supporting_items = [
            subject.evidence[evidence_id]
            for evidence_id in supporting
            if evidence_id in subject.evidence
        ]
        all_support_stale = bool(supporting_items) and all(
            item.stale for item in supporting_items
        )
        if (
            policy.revise_stale_material_claims
            and (
                claim.stale
                or claim.support_status is ClaimSupportStatus.STALE
                or all_support_stale
            )
        ):
            findings.append(
                _finding(
                    "MATERIAL_CLAIM_STALE",
                    QAFindingSeverity.ERROR,
                    "freshness",
                    "Material claim depends on stale supporting evidence.",
                    claim_id=claim.id,
                    evidence_ids=supporting,
                    rule="revise_stale_material_claims",
                )
            )

        required_confidence = _required_confidence(subject.risk_class, policy)
        if not confidence_at_least(
            claim.confidence_class,
            required_confidence,
        ):
            findings.append(
                _finding(
                    "MATERIAL_CLAIM_LOW_CONFIDENCE",
                    QAFindingSeverity.ERROR,
                    "confidence",
                    (
                        f"Material claim confidence {claim.confidence_class.value} "
                        f"is below required {required_confidence.value}."
                    ),
                    claim_id=claim.id,
                    evidence_ids=supporting,
                    rule=(
                        "sensitive_min_confidence"
                        if subject.risk_class in {RiskClass.R2, RiskClass.R3}
                        else "min_pass_confidence"
                    ),
                )
            )

    searchable = "\n".join(
        part
        for part in [
            subject.draft.title,
            subject.draft.deck or "",
            subject.draft.body,
        ]
        if part
    ).casefold()
    for phrase in subject.vertical_pack.voice.prohibited_phrases:
        if phrase.casefold() in searchable:
            findings.append(
                _finding(
                    "PROHIBITED_STYLE_PHRASE",
                    QAFindingSeverity.ERROR,
                    "style",
                    "Draft contains a prohibited vertical-pack phrase.",
                    location="draft",
                    rule="vertical_pack.voice.prohibited_phrases",
                    metadata={"phrase": phrase},
                )
            )

    if len(subject.draft.title) > subject.vertical_pack.voice.max_headline_chars:
        findings.append(
            _finding(
                "HEADLINE_TOO_LONG",
                QAFindingSeverity.ERROR,
                "style",
                "Headline exceeds the vertical-pack maximum length.",
                location="draft.title",
                rule="vertical_pack.voice.max_headline_chars",
            )
        )
    if (
        subject.draft.deck is not None
        and len(subject.draft.deck) > subject.vertical_pack.voice.max_deck_chars
    ):
        findings.append(
            _finding(
                "DECK_TOO_LONG",
                QAFindingSeverity.ERROR,
                "style",
                "Deck exceeds the vertical-pack maximum length.",
                location="draft.deck",
                rule="vertical_pack.voice.max_deck_chars",
            )
        )
    if len(subject.draft.sections) < subject.vertical_pack.voice.min_sections:
        findings.append(
            _finding(
                "TOO_FEW_SECTIONS",
                QAFindingSeverity.ERROR,
                "quality",
                "Draft has fewer sections than the vertical pack requires.",
                location="draft.sections",
                rule="vertical_pack.voice.min_sections",
            )
        )

    if subject.manifest_status is AssetManifestStatus.BLOCKED:
        findings.append(
            _finding(
                "ASSET_MANIFEST_BLOCKED",
                QAFindingSeverity.BLOCKER,
                "asset_rights",
                "Asset manifest is blocked.",
                rule="asset_manifest_status",
            )
        )
    if (
        policy.block_restricted_assets
        and subject.rights_status is AssetRightsStatus.RESTRICTED
    ):
        findings.append(
            _finding(
                "RESTRICTED_ASSET_RIGHTS",
                QAFindingSeverity.BLOCKER,
                "asset_rights",
                "At least one asset is restricted for publication.",
                rule="block_restricted_assets",
            )
        )
    elif subject.rights_status is AssetRightsStatus.REVIEW_REQUIRED:
        findings.append(
            _finding(
                "ASSET_RIGHTS_REVIEW_REQUIRED",
                QAFindingSeverity.WARNING,
                "asset_rights",
                "Asset rights need human review at Gate B.",
                rule="asset_rights_review",
            )
        )

    if subject.vertical_pack.visual.assets_required and subject.text_only:
        findings.append(
            _finding(
                "REQUIRED_ASSET_MISSING",
                QAFindingSeverity.BLOCKER,
                "asset_quality",
                "Vertical pack requires an asset but manifest is text-only.",
                rule="vertical_pack.visual.assets_required",
            )
        )

    for asset in subject.assets:
        if (
            policy.block_restricted_assets
            and asset.rights_status is AssetRightsStatus.RESTRICTED
        ):
            findings.append(
                _finding(
                    "RESTRICTED_ASSET_RIGHTS",
                    QAFindingSeverity.BLOCKER,
                    "asset_rights",
                    "Asset is restricted for publication.",
                    asset_id=asset.id,
                    rule="block_restricted_assets",
                )
            )
        if (
            subject.vertical_pack.visual.require_alt_text
            and not (asset.alt_text and asset.alt_text.strip())
        ):
            findings.append(
                _finding(
                    "ASSET_ALT_TEXT_MISSING",
                    QAFindingSeverity.ERROR,
                    "accessibility",
                    "Asset is missing required alt text.",
                    asset_id=asset.id,
                    rule="vertical_pack.visual.require_alt_text",
                )
            )
        if (
            subject.vertical_pack.visual.require_caption
            and not (asset.caption and asset.caption.strip())
        ):
            findings.append(
                _finding(
                    "ASSET_CAPTION_MISSING",
                    QAFindingSeverity.ERROR,
                    "asset_quality",
                    "Asset is missing required caption.",
                    asset_id=asset.id,
                    rule="vertical_pack.visual.require_caption",
                )
            )

    return findings


def _finding(
    code: str,
    severity: QAFindingSeverity,
    category: str,
    message: str,
    *,
    location: str | None = None,
    claim_id: UUID | None = None,
    evidence_ids: list[UUID] | None = None,
    asset_id: UUID | None = None,
    rule: str | None = None,
    metadata: dict[str, object] | None = None,
) -> QAFinding:
    return QAFinding(
        code=code,
        severity=severity,
        category=category,
        message=message,
        location=location,
        claim_id=claim_id,
        evidence_ids=evidence_ids or [],
        asset_id=asset_id,
        policy_rule=rule,
        metadata=metadata or {},
    )


def _contradiction_severity(risk_class: RiskClass) -> QAFindingSeverity:
    if risk_class in {RiskClass.R2, RiskClass.R3}:
        return QAFindingSeverity.BLOCKER
    return QAFindingSeverity.ERROR


def _required_confidence(
    risk_class: RiskClass,
    policy: EditorialQAPolicy,
) -> ConfidenceClass:
    if risk_class in {RiskClass.R2, RiskClass.R3}:
        return policy.sensitive_min_confidence
    return policy.min_pass_confidence
