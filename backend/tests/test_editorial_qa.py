from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import insert

from editorial_os_api.domain.enums import (
    ConfidenceClass,
    QAOutcome,
    RiskClass,
    WorkflowStatus,
)
from editorial_os_api.editorial_qa import (
    EditorialQAAgent,
    EditorialQAResult,
    QAAssetContext,
    QAClaimContext,
    QADraftContext,
    SemanticQAFinding,
    SemanticQAOutput,
)
from editorial_os_api.persistence.models import (
    AssetManifest,
    Claim,
    Draft,
    EditorialBrief,
    EvidenceItem,
    WorkflowRun,
    claim_evidence_links,
    draft_claim_links,
)
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.vertical_packs import VerticalPack, generic_demo_pack

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


class FixtureQAAdapter:
    name = "fixture-qa"

    def __init__(self, findings: list[SemanticQAFinding] | None = None) -> None:
        self.findings = findings or []
        self.calls = 0

    def review(
        self,
        workflow_run_id: UUID,
        *,
        draft: QADraftContext,
        claims: list[QAClaimContext],
        assets: list[QAAssetContext],
        vertical_pack: VerticalPack,
        call_key: str,
    ) -> SemanticQAOutput:
        del workflow_run_id, draft, claims, assets, vertical_pack, call_key
        self.calls += 1
        return SemanticQAOutput(findings=self.findings)


def _create_subject(
    *,
    unsupported_draft_assertion: bool = False,
    include_supporting_evidence: bool = True,
    stale: bool = False,
    contested: bool = False,
    risk_class: RiskClass = RiskClass.R0,
    confidence_class: ConfidenceClass = ConfidenceClass.C4,
) -> UUID:
    _upgrade_schema()
    pack = generic_demo_pack()

    with get_session_factory().begin() as session:
        run = WorkflowRun(
            vertical_key=pack.key,
            vertical_version=pack.version,
            status=WorkflowStatus.ASSETS_READY.value,
            risk_class=risk_class.value,
            confidence_class=confidence_class.value,
            policy_version="1",
            idempotency_key=f"qa-run-{uuid4().hex}",
            context={},
        )
        session.add(run)
        session.flush()

        brief = EditorialBrief(
            workflow_run_id=run.id,
            version=1,
            angle="Explain a verified launch.",
            locale=pack.default_locale,
            instructions={},
        )
        session.add(brief)
        session.flush()

        draft = Draft(
            workflow_run_id=run.id,
            editorial_brief_id=brief.id,
            research_brief_id=None,
            revision_of_id=None,
            version=1,
            locale=pack.default_locale,
            content_format=pack.default_format,
            vertical_pack_key=pack.key,
            vertical_pack_version=pack.version,
            input_fingerprint=f"qa-draft-{uuid4().hex}",
            title="A verified service launch",
            deck="What changed and why it matters.",
            body="The service launched after the verified announcement.",
            sections=[
                {
                    "heading": "What changed",
                    "body": "The service launched after the verified announcement.",
                    "factual_assertions": [],
                }
            ],
            seo_metadata={},
            citations=[],
            internal_link_suggestions=[],
            unsupported_factual_claims=(
                ["The service has one million paying customers."]
                if unsupported_draft_assertion
                else []
            ),
            vertical_pack_snapshot=pack.model_dump(mode="json"),
            revision_feedback=None,
            metadata_payload={},
        )
        session.add(draft)
        session.flush()

        claim = Claim(
            workflow_run_id=run.id,
            claim_key="service-launch",
            statement="The service launched after the verified announcement.",
            material=True,
            confidence_class=confidence_class.value,
            confidence_reason_codes=["fixture"],
            risk_class=risk_class.value,
            support_status=(
                "CONTESTED"
                if contested
                else "STALE" if stale else "SUPPORTED"
            ),
            stale=stale,
            contested=contested,
        )
        session.add(claim)
        session.flush()
        session.execute(
            insert(draft_claim_links).values(
                draft_id=draft.id,
                claim_id=claim.id,
                support_status=claim.support_status,
            )
        )

        if include_supporting_evidence:
            evidence = EvidenceItem(
                workflow_run_id=run.id,
                source_item_id=None,
                url="https://example.test/official-launch",
                excerpt="The service launched.",
                tier="E3",
                source_role="PRIMARY",
                stale=stale,
                extraction_method="fixture",
                metadata_payload={},
                observed_at=run.created_at,
                published_at=run.created_at,
                retain_until=None,
                redacted_at=None,
            )
            session.add(evidence)
            session.flush()
            session.execute(
                insert(claim_evidence_links).values(
                    claim_id=claim.id,
                    evidence_item_id=evidence.id,
                    stance="SUPPORTS",
                    reason_code="fixture",
                )
            )
            if contested:
                refuting = EvidenceItem(
                    workflow_run_id=run.id,
                    source_item_id=None,
                    url="https://example.test/official-correction",
                    excerpt="The launch claim is disputed.",
                    tier="E3",
                    source_role="PRIMARY",
                    stale=False,
                    extraction_method="fixture",
                    metadata_payload={},
                    observed_at=run.created_at,
                    published_at=run.created_at,
                    retain_until=None,
                    redacted_at=None,
                )
                session.add(refuting)
                session.flush()
                session.execute(
                    insert(claim_evidence_links).values(
                        claim_id=claim.id,
                        evidence_item_id=refuting.id,
                        stance="REFUTES",
                        reason_code="fixture-refutation",
                    )
                )

        manifest = AssetManifest(
            workflow_run_id=run.id,
            draft_id=draft.id,
            version=1,
            input_fingerprint=f"qa-manifest-{uuid4().hex}",
            status="READY",
            text_only=True,
            rights_status="CLEAR",
            provider_name=None,
            provider_request_count=0,
            visual_brief={"text_only": True},
            asset_ids=[],
            approval_snapshot={
                "draft": {"id": str(draft.id), "version": draft.version},
                "asset_manifest": {"version": 1},
                "assets": [],
            },
            vertical_pack_snapshot=pack.model_dump(mode="json"),
        )
        session.add(manifest)
        session.flush()
        return draft.id


def _codes(result: EditorialQAResult) -> set[str]:
    return {finding.code for finding in result.findings}


def test_clean_subject_passes_and_reaches_gate_b() -> None:
    draft_id = _create_subject()
    adapter = FixtureQAAdapter()

    result = EditorialQAAgent(get_session_factory()).review(
        draft_id,
        adapter=adapter,
    )

    assert result.outcome is QAOutcome.PASS
    assert result.gate_b_ready is True
    assert result.workflow_status == WorkflowStatus.QA_PASSED.value
    assert result.reason_codes == ["QA_POLICY_SATISFIED"]
    assert result.subject_snapshot.draft_id == draft_id
    assert adapter.calls == 1


def test_fabricated_draft_claim_blocks_with_traceable_finding() -> None:
    draft_id = _create_subject(unsupported_draft_assertion=True)

    result = EditorialQAAgent(get_session_factory()).review(
        draft_id,
        adapter=FixtureQAAdapter(),
    )

    assert result.outcome is QAOutcome.BLOCK
    assert result.workflow_status == WorkflowStatus.BLOCKED.value
    assert "UNSUPPORTED_DRAFT_ASSERTION" in _codes(result)
    finding = next(
        item
        for item in result.findings
        if item.code == "UNSUPPORTED_DRAFT_ASSERTION"
    )
    assert finding.policy_rule == "block_unsupported_material_claims"
    assert "statement" in finding.metadata


def test_missing_evidence_can_never_pass() -> None:
    draft_id = _create_subject(include_supporting_evidence=False)

    result = EditorialQAAgent(get_session_factory()).review(
        draft_id,
        adapter=FixtureQAAdapter(),
    )

    assert result.outcome is QAOutcome.BLOCK
    assert "MATERIAL_CLAIM_WITHOUT_SUPPORTING_EVIDENCE" in _codes(result)
    assert result.workflow_status == WorkflowStatus.BLOCKED.value


def test_stale_material_evidence_requires_revision() -> None:
    draft_id = _create_subject(stale=True)

    result = EditorialQAAgent(get_session_factory()).review(
        draft_id,
        adapter=FixtureQAAdapter(),
    )

    assert result.outcome is QAOutcome.REVISE
    assert "MATERIAL_CLAIM_STALE" in _codes(result)
    assert result.workflow_status == WorkflowStatus.DRAFTED.value


def test_contested_material_claim_traces_both_evidence_sides() -> None:
    draft_id = _create_subject(contested=True)

    result = EditorialQAAgent(get_session_factory()).review(
        draft_id,
        adapter=FixtureQAAdapter(),
    )

    assert result.outcome is QAOutcome.REVISE
    finding = next(
        item for item in result.findings if item.code == "MATERIAL_CLAIM_CONTESTED"
    )
    assert len(finding.evidence_ids) == 2
    assert finding.policy_rule == "revise_contested_material_claims"
    assert result.workflow_status == WorkflowStatus.DRAFTED.value


def test_semantic_headline_body_mismatch_requires_revision() -> None:
    draft_id = _create_subject()
    adapter = FixtureQAAdapter(
        [
            SemanticQAFinding(
                code="HEADLINE_BODY_MISMATCH",
                severity="ERROR",
                category="consistency",
                message="Headline promises a result that the body does not establish.",
                location="draft.title",
            )
        ]
    )

    result = EditorialQAAgent(get_session_factory()).review(
        draft_id,
        adapter=adapter,
    )

    assert result.outcome is QAOutcome.REVISE
    assert "HEADLINE_BODY_MISMATCH" in _codes(result)
    assert result.workflow_status == WorkflowStatus.DRAFTED.value


def test_high_risk_pass_still_requires_human_approval() -> None:
    draft_id = _create_subject(risk_class=RiskClass.R2)

    result = EditorialQAAgent(get_session_factory()).review(
        draft_id,
        adapter=FixtureQAAdapter(),
    )

    assert result.outcome is QAOutcome.PASS
    assert result.human_approval_required is True
    assert result.gate_b_ready is True
    assert "HIGH_RISK_HUMAN_APPROVAL_REQUIRED" in _codes(result)
    assert result.workflow_status == WorkflowStatus.QA_PASSED.value


def test_identical_retry_reuses_review_without_second_adapter_call() -> None:
    draft_id = _create_subject()
    adapter = FixtureQAAdapter()
    agent = EditorialQAAgent(get_session_factory())

    first = agent.review(draft_id, adapter=adapter)
    second = agent.review(draft_id, adapter=adapter)

    assert second.review_id == first.review_id
    assert second.review_version == first.review_version
    assert second.outcome is QAOutcome.PASS
    assert adapter.calls == 1
