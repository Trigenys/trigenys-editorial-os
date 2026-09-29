from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from editorial_os_api.domain.enums import (
    ClaimSupportStatus,
    EvidenceStance,
    EvidenceTier,
    GateOutcome,
    ResearchBriefStatus,
    RiskClass,
    SourceKind,
    WorkflowStatus,
)
from editorial_os_api.persistence.models import (
    Claim,
    EvidenceItem,
    GateDecision,
    ResearchBrief,
    Source,
    SourceItem,
    TopicCandidate,
    WorkflowRun,
    claim_evidence_links,
)
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.research_verification import (
    ClaimSeed,
    EvidenceAssessment,
    ResearchBudget,
    ResearchSourceDocument,
    ResearchVerificationAgent,
    SourceAssessmentOutput,
    UnsupportedClaimVerificationError,
    VerificationPolicy,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


@dataclass(frozen=True)
class SourceFixture:
    source_item_id: UUID
    source_name: str


def _create_approved_run(
    source_specs: list[tuple[str, EvidenceTier, str, datetime]],
    *,
    risk_class: RiskClass = RiskClass.R0,
) -> tuple[UUID, list[SourceFixture]]:
    _upgrade_schema()
    with get_session_factory().begin() as session:
        run = WorkflowRun(
            vertical_key="research-verification-fixture",
            vertical_version="1",
            status=WorkflowStatus.TOPIC_APPROVED.value,
            risk_class=risk_class.value,
            confidence_class="C1",
            policy_version="1",
            idempotency_key=f"research-run-{uuid4().hex}",
            context={},
        )
        session.add(run)
        session.flush()

        fixtures: list[SourceFixture] = []
        source_item_ids: list[str] = []
        for source_name, tier, text, published_at in source_specs:
            source = Source(
                name=source_name,
                kind=SourceKind.RSS.value,
                base_url=f"https://{source_name}.example.test/feed.xml",
                enabled=True,
                trust_tier=tier.value,
                default_evidence_tier=tier.value,
                locale="en",
                vertical_keys=["research-verification-fixture"],
                fetch_policy={},
                retention_days=30,
                redact_raw_content=False,
                config={},
                health_status="HEALTHY",
                consecutive_failures=0,
            )
            session.add(source)
            session.flush()

            item = SourceItem(
                source_id=source.id,
                external_id=f"item-{uuid4().hex}",
                identity_key=f"identity-{uuid4().hex}",
                canonical_url=f"https://{source_name}.example.test/story",
                title=f"{source_name} report",
                content_hash=f"hash-{uuid4().hex}",
                locale="en",
                raw_content=None,
                extracted_payload={"body": text, "summary": text},
                provenance={"fixture": True},
                published_at=published_at,
                observed_at=published_at,
                retain_until=None,
                redacted_at=None,
            )
            session.add(item)
            session.flush()
            fixtures.append(
                SourceFixture(
                    source_item_id=item.id,
                    source_name=source_name,
                )
            )
            source_item_ids.append(str(item.id))

        candidate = TopicCandidate(
            workflow_run_id=run.id,
            version=1,
            cluster_key=f"research-topic-{uuid4().hex}",
            title="Fixture research topic",
            proposed_angle="Explain the fixture research topic.",
            proposed_format="article",
            urgency="NORMAL",
            decision="PROPOSE",
            novelty_score=90,
            relevance_score=90,
            source_diversity_score=75,
            composite_score=88,
            risk_class=risk_class.value,
            confidence_class="C1",
            reason_codes=["fixture"],
            source_item_ids=source_item_ids,
            reason_details={},
        )
        session.add(candidate)
        session.flush()

        session.add(
            GateDecision(
                workflow_run_id=run.id,
                gate="A",
                outcome=GateOutcome.APPROVED.value,
                artifact_type="topic_candidate",
                artifact_id=candidate.id,
                artifact_version=1,
                actor_id="operator",
                reason=None,
                decided_at=NOW,
                policy_version="1",
                details={},
            )
        )
        return run.id, fixtures


class FixtureResearchAdapter:
    name = "fixture-research"

    def __init__(
        self,
        *,
        assessments: dict[str, list[EvidenceAssessment]],
        planned_claims: list[ClaimSeed] | None = None,
    ) -> None:
        self.assessments = assessments
        self.planned_claims = planned_claims or []
        self.plan_calls = 0
        self.assess_calls = 0
        self.seen_sources: list[str] = []

    def plan_claims(
        self,
        workflow_run_id: UUID,
        *,
        candidate_title: str,
        candidate_angle: str,
        sources: list[ResearchSourceDocument],
        max_claims: int,
        call_key: str,
    ) -> list[ClaimSeed]:
        del workflow_run_id, candidate_title, candidate_angle, sources, max_claims, call_key
        self.plan_calls += 1
        return list(self.planned_claims)

    def assess_source(
        self,
        workflow_run_id: UUID,
        *,
        source: ResearchSourceDocument,
        claims: list[ClaimSeed],
        call_key: str,
    ) -> SourceAssessmentOutput:
        del workflow_run_id, claims, call_key
        self.assess_calls += 1
        self.seen_sources.append(source.source_name)
        return SourceAssessmentOutput(
            assessments=list(self.assessments.get(source.source_name, []))
        )


def _claim(
    *,
    risk_class: RiskClass = RiskClass.R0,
) -> ClaimSeed:
    return ClaimSeed(
        claim_key="launch-date",
        statement="The service launched on 29 September 2026.",
        material=True,
        risk_class=risk_class,
    )


def _support(excerpt: str) -> EvidenceAssessment:
    return EvidenceAssessment(
        claim_key="launch-date",
        stance=EvidenceStance.SUPPORTS,
        excerpt=excerpt,
        reason_code="EXPLICIT_STATEMENT",
    )


def _refute(excerpt: str) -> EvidenceAssessment:
    return EvidenceAssessment(
        claim_key="launch-date",
        stance=EvidenceStance.REFUTES,
        excerpt=excerpt,
        reason_code="EXPLICIT_CONTRADICTION",
    )


def test_primary_source_then_secondary_corroboration_reaches_verified() -> None:
    primary_text = "The service launched on 29 September 2026."
    secondary_text = "Independent reporting confirms the service launched on 29 September 2026."
    run_id, _ = _create_approved_run(
        [
            ("secondary", EvidenceTier.E2, secondary_text, NOW - timedelta(hours=1)),
            ("primary", EvidenceTier.E3, primary_text, NOW - timedelta(minutes=30)),
        ]
    )
    adapter = FixtureResearchAdapter(
        assessments={
            "primary": [_support(primary_text)],
            "secondary": [_support(secondary_text)],
        }
    )

    result = ResearchVerificationAgent(get_session_factory()).verify(
        run_id,
        adapter=adapter,
        claim_seeds=[_claim()],
        now=NOW,
    )

    assert adapter.seen_sources == ["primary", "secondary"]
    assert result.status is ResearchBriefStatus.VERIFIED
    assert result.confidence_class.value == "C4"
    assert result.review_required is False
    assert result.workflow_status == WorkflowStatus.VERIFIED.value
    assert len(result.claim_ids) == 1
    assert len(result.evidence_ids) == 2

    with get_session_factory()() as session:
        claim = session.get(Claim, result.claim_ids[0])
        assert claim is not None
        assert claim.support_status == ClaimSupportStatus.SUPPORTED.value
        assert claim.confidence_class == "C4"

        evidence = list(
            session.scalars(
                select(EvidenceItem)
                .where(EvidenceItem.id.in_(result.evidence_ids))
                .order_by(EvidenceItem.source_role)
            )
        )
        assert {item.source_role for item in evidence} == {"PRIMARY", "SECONDARY"}

        link_count = session.scalar(
            select(func.count()).select_from(claim_evidence_links).where(
                claim_evidence_links.c.claim_id == claim.id
            )
        )
        assert link_count == 2


def test_conflicting_credible_evidence_is_surfaced_and_blocks_for_review() -> None:
    support_text = "The service launched on 29 September 2026."
    refute_text = "The service did not launch on 29 September 2026."
    run_id, _ = _create_approved_run(
        [
            ("primary", EvidenceTier.E3, support_text, NOW - timedelta(hours=1)),
            ("secondary", EvidenceTier.E2, refute_text, NOW - timedelta(minutes=30)),
        ]
    )
    adapter = FixtureResearchAdapter(
        assessments={
            "primary": [_support(support_text)],
            "secondary": [_refute(refute_text)],
        }
    )

    result = ResearchVerificationAgent(get_session_factory()).verify(
        run_id,
        adapter=adapter,
        claim_seeds=[_claim()],
        now=NOW,
    )

    assert result.status is ResearchBriefStatus.REVIEW_REQUIRED
    assert result.confidence_class.value == "C1"
    assert result.review_required is True
    assert len(result.contradiction_claim_ids) == 1
    assert "MATERIAL_CONTRADICTION" in result.reason_codes
    assert result.workflow_status == WorkflowStatus.BLOCKED.value

    with get_session_factory()() as session:
        claim = session.get(Claim, result.claim_ids[0])
        assert claim is not None
        assert claim.contested is True
        assert claim.support_status == ClaimSupportStatus.CONTESTED.value


def test_missing_support_is_insufficient_and_cannot_be_human_overridden() -> None:
    text = "This source discusses a different subject."
    run_id, _ = _create_approved_run(
        [("primary", EvidenceTier.E3, text, NOW - timedelta(hours=1))]
    )
    adapter = FixtureResearchAdapter(
        assessments={
            "primary": [
                EvidenceAssessment(
                    claim_key="launch-date",
                    stance=EvidenceStance.NO_EVIDENCE,
                    excerpt=None,
                    reason_code="NOT_FOUND",
                )
            ]
        }
    )
    agent = ResearchVerificationAgent(get_session_factory())

    result = agent.verify(
        run_id,
        adapter=adapter,
        claim_seeds=[_claim()],
        now=NOW,
    )

    assert result.status is ResearchBriefStatus.INSUFFICIENT
    assert len(result.unsupported_claim_ids) == 1
    assert result.workflow_status == WorkflowStatus.BLOCKED.value

    with pytest.raises(UnsupportedClaimVerificationError):
        agent.resolve_human_review(
            result.research_brief_id,
            actor_id="reviewer",
            reason="Proceed anyway",
        )


def test_stale_support_is_low_confidence_and_routes_to_review() -> None:
    text = "The service launched on 29 September 2026."
    run_id, _ = _create_approved_run(
        [("primary", EvidenceTier.E3, text, NOW - timedelta(days=10))]
    )
    adapter = FixtureResearchAdapter(
        assessments={"primary": [_support(text)]}
    )

    result = ResearchVerificationAgent(get_session_factory()).verify(
        run_id,
        adapter=adapter,
        claim_seeds=[_claim()],
        policy=VerificationPolicy(stale_after_hours=24),
        now=NOW,
    )

    assert result.status is ResearchBriefStatus.REVIEW_REQUIRED
    assert result.confidence_class.value == "C1"
    assert len(result.stale_claim_ids) == 1
    assert "LOW_CONFIDENCE_REVIEW" in result.reason_codes
    assert result.workflow_status == WorkflowStatus.BLOCKED.value


def test_sensitive_high_confidence_research_requires_human_review_then_resolves() -> None:
    text = "The service launched on 29 September 2026."
    run_id, _ = _create_approved_run(
        [("primary", EvidenceTier.E4, text, NOW - timedelta(hours=1))],
        risk_class=RiskClass.R2,
    )
    adapter = FixtureResearchAdapter(
        assessments={"primary": [_support(text)]}
    )
    agent = ResearchVerificationAgent(get_session_factory())

    result = agent.verify(
        run_id,
        adapter=adapter,
        claim_seeds=[_claim(risk_class=RiskClass.R2)],
        now=NOW,
    )

    assert result.status is ResearchBriefStatus.REVIEW_REQUIRED
    assert result.confidence_class.value == "C4"
    assert result.risk_class is RiskClass.R2
    assert "SENSITIVE_RISK_REVIEW" in result.reason_codes
    assert result.workflow_status == WorkflowStatus.BLOCKED.value

    reviewed = agent.resolve_human_review(
        result.research_brief_id,
        actor_id="senior-editor",
        reason="Evidence reviewed and framing approved.",
    )
    assert reviewed.status is ResearchBriefStatus.REVIEWED
    assert reviewed.review_required is False
    assert reviewed.workflow_status == WorkflowStatus.VERIFIED.value


def test_research_source_budget_is_strictly_bounded() -> None:
    text = "The service launched on 29 September 2026."
    run_id, _ = _create_approved_run(
        [
            ("source-a", EvidenceTier.E2, text, NOW - timedelta(minutes=10)),
            ("source-b", EvidenceTier.E2, text, NOW - timedelta(minutes=20)),
            ("source-c", EvidenceTier.E2, text, NOW - timedelta(minutes=30)),
        ]
    )
    adapter = FixtureResearchAdapter(
        assessments={
            "source-a": [_support(text)],
            "source-b": [_support(text)],
            "source-c": [_support(text)],
        }
    )

    result = ResearchVerificationAgent(get_session_factory()).verify(
        run_id,
        adapter=adapter,
        claim_seeds=[_claim()],
        budget=ResearchBudget(
            max_sources=1,
            max_claims=2,
            max_evidence_items=10,
            max_adapter_calls=1,
        ),
        now=NOW,
    )

    assert adapter.assess_calls == 1
    assert "SOURCE_BUDGET_LIMIT_REACHED" in result.reason_codes
    with get_session_factory()() as session:
        brief = session.get(ResearchBrief, result.research_brief_id)
        assert brief is not None
        assert brief.budget_usage["sources_examined"] == 1
        assert brief.budget_usage["adapter_calls"] == 1


def test_non_verbatim_model_excerpt_is_rejected_as_evidence() -> None:
    text = "The service launched on 29 September 2026."
    run_id, _ = _create_approved_run(
        [("primary", EvidenceTier.E3, text, NOW - timedelta(hours=1))]
    )
    adapter = FixtureResearchAdapter(
        assessments={
            "primary": [
                _support("An invented sentence that does not exist in the source.")
            ]
        }
    )

    result = ResearchVerificationAgent(get_session_factory()).verify(
        run_id,
        adapter=adapter,
        claim_seeds=[_claim()],
        now=NOW,
    )

    assert result.status is ResearchBriefStatus.INSUFFICIENT
    assert len(result.evidence_ids) == 0
    assert "EXCERPT_REJECTED_NOT_IN_SOURCE" in result.reason_codes


def test_retry_reuses_persisted_research_without_new_adapter_calls() -> None:
    primary_text = "The service launched on 29 September 2026."
    secondary_text = "Independent reporting confirms the service launched on 29 September 2026."
    run_id, _ = _create_approved_run(
        [
            ("primary", EvidenceTier.E3, primary_text, NOW - timedelta(minutes=20)),
            ("secondary", EvidenceTier.E2, secondary_text, NOW - timedelta(minutes=10)),
        ]
    )
    adapter = FixtureResearchAdapter(
        assessments={
            "primary": [_support(primary_text)],
            "secondary": [_support(secondary_text)],
        }
    )
    agent = ResearchVerificationAgent(get_session_factory())
    claim = _claim()

    first = agent.verify(
        run_id,
        adapter=adapter,
        claim_seeds=[claim],
        now=NOW,
    )
    calls_after_first = adapter.assess_calls

    second = agent.verify(
        run_id,
        adapter=adapter,
        claim_seeds=[claim],
        now=NOW,
    )

    assert second.research_brief_id == first.research_brief_id
    assert adapter.assess_calls == calls_after_first
