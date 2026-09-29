from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from editorial_os_api.domain.enums import (
    AuditActorKind,
    GateOutcome,
    SourceKind,
    TopicDecision,
    TopicUrgency,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.editorial_intelligence import (
    CandidateVersionConflictError,
    DecisionThresholds,
    EditorialIntelligenceAgent,
    ScoreWeights,
    VerticalIntelligencePolicy,
)
from editorial_os_api.model_gateway import (
    BudgetLedger,
    BudgetPolicy,
    ModelGateway,
    ModelPolicy,
    ModelRoute,
    ModelTask,
)
from editorial_os_api.model_gateway.fake import DeterministicFakeModel
from editorial_os_api.orchestration import (
    InvalidTransitionError,
    PostgresWorkflowEngine,
    WorkflowCommand,
)
from editorial_os_api.persistence.models import (
    AuditEvent,
    Source,
    SourceItem,
    TopicCandidate,
    WorkflowRun,
)
from editorial_os_api.persistence.session import get_session_factory

BACKEND_DIR = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 29, 5, 0, tzinfo=UTC)


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _create_run(
    *,
    vertical_key: str = "technology",
    vertical_version: str = "1",
) -> UUID:
    _upgrade_schema()
    run = WorkflowRun(
        vertical_key=vertical_key,
        vertical_version=vertical_version,
        status=WorkflowStatus.INGESTED.value,
        risk_class="R0",
        confidence_class="C0",
        policy_version="1",
        idempotency_key=f"intel-run-{uuid4().hex}",
        context={},
    )
    with get_session_factory().begin() as session:
        session.add(run)
        session.flush()
        return run.id


def _source_item(
    *,
    title: str,
    summary: str,
    published_at: datetime,
    source_name: str,
    vertical_key: str = "technology",
    locale: str = "en",
) -> UUID:
    _upgrade_schema()
    with get_session_factory().begin() as session:
        source = Source(
            name=f"{source_name}-{uuid4().hex}",
            kind=SourceKind.RSS.value,
            base_url="https://example.test/feed.xml",
            enabled=True,
            trust_tier="E2",
            default_evidence_tier="E2",
            locale=locale,
            vertical_keys=[vertical_key],
            fetch_policy={},
            retention_days=7,
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
            canonical_url=f"https://example.test/story/{uuid4().hex}",
            title=title,
            content_hash=f"hash-{uuid4().hex}",
            locale=locale,
            raw_content=None,
            extracted_payload={"summary": summary},
            provenance={"fixture": True},
            published_at=published_at,
            observed_at=published_at,
            retain_until=None,
            redacted_at=None,
        )
        session.add(item)
        session.flush()
        return item.id


def _policy(
    *,
    vertical_key: str = "technology",
    version: str = "1",
    priority_terms: list[str] | None = None,
    weights: ScoreWeights | None = None,
    thresholds: DecisionThresholds | None = None,
    use_model_strategy: bool = False,
) -> VerticalIntelligencePolicy:
    return VerticalIntelligencePolicy(
        vertical_key=vertical_key,
        version=version,
        eligible_locales=["en"],
        priority_terms=priority_terms or [],
        supported_formats=["article", "brief"],
        default_format="article",
        weights=weights or ScoreWeights(),
        thresholds=thresholds or DecisionThresholds(),
        use_model_strategy=use_model_strategy,
    )


def _gateway(run_id: UUID, response: str) -> ModelGateway:
    del run_id
    return ModelGateway(
        DeterministicFakeModel([response], cost_usd=Decimal("0.001")),
        model_policy=ModelPolicy(
            routes={
                ModelTask.EDITORIAL_INTELLIGENCE: ModelRoute(
                    name="fixture-intelligence",
                    model="fixture/model",
                    max_call_cost_usd=Decimal("0.05"),
                )
            }
        ),
        budget_policy=BudgetPolicy(
            per_run_usd=Decimal("1.00"),
            default_per_agent_usd=Decimal("0.50"),
        ),
        budget_ledger=BudgetLedger(get_session_factory()),
    )


def test_duplicate_reports_collapse_into_one_explainable_topic_candidate() -> None:
    run_id = _create_run()
    first = _source_item(
        title="Cloudflare launches new developer platform in Africa",
        summary="Cloudflare launches a developer platform for African teams.",
        published_at=NOW - timedelta(hours=1),
        source_name="source-a",
    )
    second = _source_item(
        title="Cloudflare launches developer platform for teams in Africa",
        summary="A new Cloudflare developer platform targets teams across Africa.",
        published_at=NOW - timedelta(hours=2),
        source_name="source-b",
    )

    result = EditorialIntelligenceAgent(get_session_factory()).analyze(
        run_id,
        [first, second],
        policy=_policy(priority_terms=["cloudflare", "africa"]),
        now=NOW,
    )

    assert result.decision is TopicDecision.PROPOSE
    assert result.pending_gate == "A"
    assert len(result.source_item_ids) == 2
    assert "CROSS_SOURCE_CLUSTER" in result.reason_codes
    assert "NOVEL_TOPIC" in result.reason_codes

    with get_session_factory()() as session:
        count = session.scalar(
            select(func.count())
            .select_from(TopicCandidate)
            .where(TopicCandidate.workflow_run_id == run_id)
        )
        assert count == 1
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        assert run.status == WorkflowStatus.CANDIDATE.value


def test_stale_story_is_not_proposed_for_gate_a() -> None:
    run_id = _create_run()
    item_id = _source_item(
        title="Old framework release remains available",
        summary="The framework release was published several days ago.",
        published_at=NOW - timedelta(days=10),
        source_name="stale-source",
    )

    result = EditorialIntelligenceAgent(get_session_factory()).analyze(
        run_id,
        [item_id],
        policy=_policy(
            priority_terms=["framework"],
            thresholds=DecisionThresholds(
                propose_min=70,
                watch_min=30,
                stale_after_hours=48,
            ),
        ),
        now=NOW,
    )

    assert result.decision is TopicDecision.WATCH
    assert result.pending_gate is None
    assert "STALE_SIGNAL" in result.reason_codes
    with get_session_factory()() as session:
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        assert run.status == WorkflowStatus.INGESTED.value


def test_recent_duplicate_topic_is_downgraded_to_watch() -> None:
    first_run = _create_run()
    first_item = _source_item(
        title="FastAPI ships a new release with performance improvements",
        summary="FastAPI published a release focused on performance improvements.",
        published_at=NOW - timedelta(hours=2),
        source_name="primary",
    )
    first = EditorialIntelligenceAgent(get_session_factory()).analyze(
        first_run,
        [first_item],
        policy=_policy(priority_terms=["fastapi", "performance"]),
        now=NOW,
    )
    assert first.decision is TopicDecision.PROPOSE

    second_run = _create_run()
    second_item = _source_item(
        title="FastAPI ships new release with performance improvements",
        summary="The latest FastAPI release focuses on performance improvements.",
        published_at=NOW - timedelta(minutes=20),
        source_name="secondary",
    )
    second = EditorialIntelligenceAgent(get_session_factory()).analyze(
        second_run,
        [second_item],
        policy=_policy(priority_terms=["fastapi", "performance"]),
        now=NOW,
    )

    assert second.decision is TopicDecision.WATCH
    assert any(
        code in second.reason_codes
        for code in {"DUPLICATE_RECENT_TOPIC", "SIMILAR_RECENT_TOPIC"}
    )


def test_vertical_weights_change_scores_without_core_code_forks() -> None:
    item_a = _source_item(
        title="Regional startup raises funding for logistics platform",
        summary="The startup announced funding for a logistics platform.",
        published_at=NOW - timedelta(hours=1),
        source_name="weights-a",
        vertical_key="startups",
    )
    run_a = _create_run(vertical_key="startups")
    relevance_heavy = EditorialIntelligenceAgent(get_session_factory()).analyze(
        run_a,
        [item_a],
        policy=_policy(
            vertical_key="startups",
            priority_terms=["cybersecurity"],
            weights=ScoreWeights(novelty=0.1, relevance=0.8, source_diversity=0.1),
        ),
        now=NOW,
    )

    item_b = _source_item(
        title="Regional startup raises funding for logistics platform",
        summary="The startup announced funding for a logistics platform.",
        published_at=NOW - timedelta(hours=1),
        source_name="weights-b",
        vertical_key="business",
    )
    run_b = _create_run(vertical_key="business")
    novelty_heavy = EditorialIntelligenceAgent(get_session_factory()).analyze(
        run_b,
        [item_b],
        policy=_policy(
            vertical_key="business",
            priority_terms=["cybersecurity"],
            weights=ScoreWeights(novelty=0.8, relevance=0.1, source_diversity=0.1),
        ),
        now=NOW,
    )

    assert novelty_heavy.composite_score > relevance_heavy.composite_score
    assert relevance_heavy.decision is not TopicDecision.PROPOSE
    assert novelty_heavy.decision is TopicDecision.PROPOSE


def test_model_enriches_strategy_but_cannot_change_deterministic_decision() -> None:
    run_id = _create_run()
    item_id = _source_item(
        title="Cloud platform adds a new observability feature",
        summary="The platform announced a new observability feature for developers.",
        published_at=NOW - timedelta(hours=1),
        source_name="model-source",
    )
    gateway = _gateway(
        run_id,
        (
            '{"proposed_angle":"What the observability change means for small teams",'
            '"proposed_format":"brief","urgency":"HIGH"}'
        ),
    )

    result = EditorialIntelligenceAgent(
        get_session_factory(),
        model_gateway=gateway,
    ).analyze(
        run_id,
        [item_id],
        policy=_policy(
            priority_terms=["observability", "developers"],
            use_model_strategy=True,
        ),
        now=NOW,
    )

    assert result.decision is TopicDecision.PROPOSE
    assert result.proposed_angle == "What the observability change means for small teams"
    assert result.proposed_format == "brief"
    assert result.urgency is TopicUrgency.HIGH
    assert "MODEL_STRATEGY_ENRICHED" in result.reason_codes


def test_operator_can_edit_angle_and_stale_version_cannot_be_approved() -> None:
    run_id = _create_run()
    item_id = _source_item(
        title="Database project announces a major release",
        summary="The database project announced a major release for developers.",
        published_at=NOW - timedelta(hours=1),
        source_name="operator-source",
    )
    agent = EditorialIntelligenceAgent(get_session_factory())
    proposed = agent.analyze(
        run_id,
        [item_id],
        policy=_policy(priority_terms=["database", "developers"]),
        now=NOW,
    )

    edited = agent.edit_angle(
        proposed.candidate_id,
        expected_version=1,
        proposed_angle="What this database release changes for African developer teams",
        actor_id="operator-1",
    )

    assert edited.candidate_version == 2
    assert edited.proposed_angle.startswith("What this database release")
    assert "OPERATOR_EDITED_ANGLE" in edited.reason_codes

    with pytest.raises(CandidateVersionConflictError):
        agent.decide_gate_a(
            proposed.candidate_id,
            expected_version=1,
            actor_id="operator-1",
            outcome=GateOutcome.APPROVED,
        )

    agent.decide_gate_a(
        proposed.candidate_id,
        expected_version=2,
        actor_id="operator-1",
        outcome=GateOutcome.APPROVED,
    )
    with get_session_factory()() as session:
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        assert run.status == WorkflowStatus.TOPIC_APPROVED.value
        audits = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.workflow_run_id == run_id,
                    AuditEvent.event_type == "topic_candidate.angle.edited",
                )
            )
        )
        assert len(audits) == 1


def test_low_confidence_candidate_cannot_skip_gate_a() -> None:
    run_id = _create_run()
    item_id = _source_item(
        title="Runtime publishes a new stable release",
        summary="The runtime announced a stable release.",
        published_at=NOW - timedelta(hours=1),
        source_name="gate-source",
    )
    agent = EditorialIntelligenceAgent(get_session_factory())
    result = agent.analyze(
        run_id,
        [item_id],
        policy=_policy(priority_terms=["runtime"]),
        now=NOW,
    )

    with get_session_factory()() as session:
        candidate = session.get(TopicCandidate, result.candidate_id)
        assert candidate is not None
        assert candidate.confidence_class == "C1"

    engine = PostgresWorkflowEngine(get_session_factory())
    with pytest.raises(InvalidTransitionError):
        engine.apply(
            run_id,
            WorkflowCommand(
                action_key=f"illegal-verify-{uuid4().hex}",
                action_type=WorkflowActionType.VERIFICATION_COMPLETED,
                actor_kind=AuditActorKind.AGENT,
                actor_id="research-verification",
                payload={},
            ),
        )
