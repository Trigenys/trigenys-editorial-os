from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from editorial_os_api.domain.enums import (
    AssetKind,
    AssetManifestStatus,
    AssetOrigin,
    AssetRightsStatus,
    ClaimSupportStatus,
    ConfidenceClass,
    RiskClass,
    WorkflowStatus,
)
from editorial_os_api.editorial_qa.contracts import (
    QAAssetContext,
    QAClaimContext,
    QADraftContext,
    QAEvidenceContext,
    QASubjectSnapshot,
)
from editorial_os_api.editorial_qa.policy import EditorialQAPolicy
from editorial_os_api.persistence.models import (
    Asset,
    AssetManifest,
    Claim,
    Draft,
    EditorialQAReview,
    EvidenceItem,
    WorkflowRun,
    claim_evidence_links,
    draft_claim_links,
)
from editorial_os_api.vertical_packs import VerticalPack

_CONFIDENCE_RANK = {
    ConfidenceClass.C0: 0,
    ConfidenceClass.C1: 1,
    ConfidenceClass.C2: 2,
    ConfidenceClass.C3: 3,
    ConfidenceClass.C4: 4,
}
_RISK_RANK = {
    RiskClass.R0: 0,
    RiskClass.R1: 1,
    RiskClass.R2: 2,
    RiskClass.R3: 3,
}


class QASubjectLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class QASubject:
    workflow_run_id: UUID
    workflow_status: WorkflowStatus
    draft: QADraftContext
    manifest_id: UUID
    manifest_version: int
    manifest_status: AssetManifestStatus
    rights_status: AssetRightsStatus
    text_only: bool
    claims: list[QAClaimContext]
    assets: list[QAAssetContext]
    evidence: dict[UUID, QAEvidenceContext]
    vertical_pack: VerticalPack
    confidence_class: ConfidenceClass
    risk_class: RiskClass
    snapshot: QASubjectSnapshot
    fingerprint: str
    existing_review_id: UUID | None = None


def load_subject(
    session: Session,
    draft_id: UUID,
    *,
    manifest_id: UUID | None,
    policy: EditorialQAPolicy,
    adapter_name: str,
) -> QASubject:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise QASubjectLoadError(f"Draft {draft_id} does not exist.")

    run = session.get(WorkflowRun, draft.workflow_run_id)
    if run is None:
        raise QASubjectLoadError("Draft workflow run does not exist.")

    manifest = _manifest_for_draft(session, draft, manifest_id=manifest_id)
    pack = _vertical_pack(draft)
    draft_context = QADraftContext(
        id=draft.id,
        version=draft.version,
        locale=draft.locale,
        content_format=draft.content_format,
        title=draft.title,
        deck=draft.deck,
        body=draft.body,
        sections=list(draft.sections),
        unsupported_factual_claims=list(draft.unsupported_factual_claims),
    )
    claims, evidence = _claim_contexts(session, draft)
    assets = _asset_contexts(session, manifest)
    confidence = _overall_confidence(run, claims)
    risk = _overall_risk(run, claims)
    snapshot = QASubjectSnapshot(
        draft_id=draft.id,
        draft_version=draft.version,
        manifest_id=manifest.id,
        manifest_version=manifest.version,
        asset_ids=[item.id for item in assets],
        claim_ids=[item.id for item in claims],
        evidence_ids=sorted(evidence, key=str),
    )
    fingerprint = _fingerprint(
        draft=draft_context,
        manifest=manifest,
        claims=claims,
        assets=assets,
        evidence=evidence,
        vertical_pack=pack,
        policy=policy,
        adapter_name=adapter_name,
    )
    existing = session.scalar(
        select(EditorialQAReview).where(
            EditorialQAReview.workflow_run_id == run.id,
            EditorialQAReview.draft_id == draft.id,
            EditorialQAReview.manifest_id == manifest.id,
            EditorialQAReview.input_fingerprint == fingerprint,
        )
    )
    return QASubject(
        workflow_run_id=run.id,
        workflow_status=WorkflowStatus(run.status),
        draft=draft_context,
        manifest_id=manifest.id,
        manifest_version=manifest.version,
        manifest_status=AssetManifestStatus(manifest.status),
        rights_status=AssetRightsStatus(manifest.rights_status),
        text_only=manifest.text_only,
        claims=claims,
        assets=assets,
        evidence=evidence,
        vertical_pack=pack,
        confidence_class=confidence,
        risk_class=risk,
        snapshot=snapshot,
        fingerprint=fingerprint,
        existing_review_id=existing.id if existing is not None else None,
    )


def _manifest_for_draft(
    session: Session,
    draft: Draft,
    *,
    manifest_id: UUID | None,
) -> AssetManifest:
    if manifest_id is not None:
        manifest = session.get(AssetManifest, manifest_id)
    else:
        manifest = session.scalar(
            select(AssetManifest)
            .where(AssetManifest.draft_id == draft.id)
            .order_by(AssetManifest.version.desc())
            .limit(1)
        )
    if manifest is None:
        raise QASubjectLoadError("Draft has no asset manifest.")
    if (
        manifest.draft_id != draft.id
        or manifest.workflow_run_id != draft.workflow_run_id
    ):
        raise QASubjectLoadError("Asset manifest does not belong to the draft.")
    return manifest


def _vertical_pack(draft: Draft) -> VerticalPack:
    try:
        return VerticalPack.model_validate(draft.vertical_pack_snapshot)
    except Exception as exc:
        raise QASubjectLoadError(
            "Draft does not contain a valid vertical-pack snapshot."
        ) from exc


def _claim_contexts(
    session: Session,
    draft: Draft,
) -> tuple[list[QAClaimContext], dict[UUID, QAEvidenceContext]]:
    claim_ids = list(
        session.scalars(
            select(draft_claim_links.c.claim_id).where(
                draft_claim_links.c.draft_id == draft.id
            )
        )
    )
    if not claim_ids:
        return [], {}

    claims = list(
        session.scalars(
            select(Claim)
            .where(Claim.id.in_(claim_ids))
            .order_by(Claim.claim_key)
        )
    )
    rows = session.execute(
        select(
            claim_evidence_links.c.claim_id,
            claim_evidence_links.c.evidence_item_id,
            claim_evidence_links.c.stance,
        ).where(claim_evidence_links.c.claim_id.in_(claim_ids))
    ).all()
    evidence_ids = {row.evidence_item_id for row in rows}
    evidence_models = list(
        session.scalars(
            select(EvidenceItem).where(EvidenceItem.id.in_(evidence_ids))
        )
    )
    evidence = {
        item.id: QAEvidenceContext(
            id=item.id,
            url=item.url,
            tier=item.tier,
            stale=item.stale,
        )
        for item in evidence_models
    }
    supports: dict[UUID, list[UUID]] = {claim_id: [] for claim_id in claim_ids}
    refutes: dict[UUID, list[UUID]] = {claim_id: [] for claim_id in claim_ids}
    for row in rows:
        if row.stance == "SUPPORTS":
            supports.setdefault(row.claim_id, []).append(row.evidence_item_id)
        elif row.stance == "REFUTES":
            refutes.setdefault(row.claim_id, []).append(row.evidence_item_id)

    contexts = [
        QAClaimContext(
            id=claim.id,
            claim_key=claim.claim_key,
            statement=claim.statement,
            material=claim.material,
            support_status=ClaimSupportStatus(claim.support_status),
            confidence_class=ConfidenceClass(claim.confidence_class),
            risk_class=RiskClass(claim.risk_class),
            stale=claim.stale,
            contested=claim.contested,
            supporting_evidence_ids=supports.get(claim.id, []),
            refuting_evidence_ids=refutes.get(claim.id, []),
        )
        for claim in claims
    ]
    return contexts, evidence


def _asset_contexts(
    session: Session,
    manifest: AssetManifest,
) -> list[QAAssetContext]:
    assets = list(
        session.scalars(
            select(Asset)
            .where(Asset.manifest_id == manifest.id)
            .order_by(Asset.version, Asset.slot)
        )
    )
    return [
        QAAssetContext(
            id=asset.id,
            version=asset.version,
            slot=asset.slot,
            kind=AssetKind(asset.kind),
            origin=AssetOrigin(asset.origin),
            rights_status=AssetRightsStatus(asset.rights_status),
            alt_text=asset.alt_text,
            caption=asset.caption,
            filename=asset.filename,
        )
        for asset in assets
    ]


def _overall_confidence(
    run: WorkflowRun,
    claims: list[QAClaimContext],
) -> ConfidenceClass:
    values = [
        ConfidenceClass(run.confidence_class),
        *(item.confidence_class for item in claims if item.material),
    ]
    return min(values, key=lambda item: _CONFIDENCE_RANK[item])


def _overall_risk(
    run: WorkflowRun,
    claims: list[QAClaimContext],
) -> RiskClass:
    values = [
        RiskClass(run.risk_class),
        *(item.risk_class for item in claims if item.material),
    ]
    return max(values, key=lambda item: _RISK_RANK[item])


def _fingerprint(
    *,
    draft: QADraftContext,
    manifest: AssetManifest,
    claims: list[QAClaimContext],
    assets: list[QAAssetContext],
    evidence: dict[UUID, QAEvidenceContext],
    vertical_pack: VerticalPack,
    policy: EditorialQAPolicy,
    adapter_name: str,
) -> str:
    payload = {
        "draft": draft.model_dump(mode="json"),
        "manifest": {
            "id": str(manifest.id),
            "version": manifest.version,
            "status": manifest.status,
            "rights_status": manifest.rights_status,
            "text_only": manifest.text_only,
        },
        "claims": [item.model_dump(mode="json") for item in claims],
        "assets": [item.model_dump(mode="json") for item in assets],
        "evidence": [
            item.model_dump(mode="json")
            for item in sorted(evidence.values(), key=lambda value: str(value.id))
        ],
        "vertical_pack": vertical_pack.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
        "adapter_name": adapter_name,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
