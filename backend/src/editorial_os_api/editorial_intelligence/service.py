from __future__ import annotations

import json
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import (
    AuditActorKind,
    ConfidenceClass,
    GateKind,
    GateOutcome,
    TopicDecision,
    TopicUrgency,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.editorial_intelligence.contracts import (
    EditorialIntelligenceResult,
    EditorialStrategyOutput,
    SignalDocument,
    VerticalIntelligencePolicy,
)
from editorial_os_api.editorial_intelligence.scoring import (
    cluster_documents,
    cluster_key,
    decide,
    representative_title,
    score_cluster,
)
from editorial_os_api.model_gateway import (
    BudgetExceededError,
    ModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
    ModelRole,
    ModelTask,
    StructuredOutputError,
)
from editorial_os_api.observability import ObservabilityHub, ProductTelemetryEvent
from editorial_os_api.orchestration import (
    GateResume,
    InvalidTransitionError,
    PostgresWorkflowEngine,
    WorkflowCommand,
)
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import (
    AuditEvent,
    Source,
    SourceItem,
    TopicCandidate,
    WorkflowRun,
)


class EditorialIntelligenceError(RuntimeError):
    pass


class CandidateVersionConflictError(EditorialIntelligenceError):
    pass


class EditorialIntelligenceAgent:
    agent_id = "editorial-intelligence"

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        workflow_engine: PostgresWorkflowEngine | None = None,
        model_gateway: ModelGateway | None = None,
        observability: ObservabilityHub | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._workflow_engine = workflow_engine or PostgresWorkflowEngine(session_factory)
        self._model_gateway = model_gateway
        self._observability = observability or ObservabilityHub()

    def analyze(
        self,
        workflow_run_id: UUID,
        source_item_ids: list[UUID],
        *,
        policy: VerticalIntelligencePolicy,
        now: datetime | None = None,
    ) -> EditorialIntelligenceResult:
        if not source_item_ids:
            raise EditorialIntelligenceError("At least one source item is required.")

        observed_now = now or utcnow()
        with self._session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise EditorialIntelligenceError(f"Unknown workflow run: {workflow_run_id}")
            if WorkflowStatus(run.status) not in {
                WorkflowStatus.INGESTED,
                WorkflowStatus.CANDIDATE,
            }:
                raise EditorialIntelligenceError(
                    f"Editorial intelligence is not legal from {run.status}."
                )
            if run.vertical_key != policy.vertical_key:
                raise EditorialIntelligenceError(
                    "Vertical policy does not match workflow vertical."
                )
            if run.vertical_version != policy.version:
                raise EditorialIntelligenceError(
                    "Vertical policy version does not match workflow vertical version."
                )
            documents = self._load_documents(
                session,
                source_item_ids,
                policy=policy,
            )
            recent_topics = self._recent_topics(
                session,
                run=run,
                policy=policy,
                now=observed_now,
            )
            risk_class = run.risk_class

        if not documents:
            raise EditorialIntelligenceError(
                "No source items are eligible for this vertical policy."
            )

        clusters = cluster_documents(
            documents,
            threshold=policy.cluster_similarity_threshold,
        )
        selected = max(
            clusters,
            key=lambda group: (
                len(group),
                max(document.observed_at_iso for document in group),
                cluster_key(group),
            ),
        )
        selected_key = cluster_key(selected)

        with self._session_factory() as session:
            existing = session.scalar(
                select(TopicCandidate).where(
                    TopicCandidate.workflow_run_id == workflow_run_id,
                    TopicCandidate.cluster_key == selected_key,
                )
            )
            if existing is not None:
                return self._result(existing)

        score = score_cluster(
            selected,
            policy=policy,
            recent_topics=recent_topics,
            now=observed_now,
        )
        decision = decide(score, policy=policy)
        title = representative_title(selected)
        angle = f"Explain {title} and why it matters for this audience."
        proposed_format = policy.default_format
        urgency = self._default_urgency(selected, score.stale, score.novelty, observed_now)
        reason_codes = list(score.reason_codes)

        if len(clusters) > 1:
            reason_codes.append("MULTIPLE_CLUSTERS_INPUT_REDUCED")

        if self._model_gateway is not None and policy.use_model_strategy:
            try:
                strategy = self._model_strategy(
                    workflow_run_id,
                    title=title,
                    decision=decision,
                    score=score.composite,
                    source_count=len(selected),
                    policy=policy,
                    call_key=f"editorial-intelligence:{selected_key}:{policy.version}",
                )
                angle = strategy.proposed_angle
                if strategy.proposed_format in policy.supported_formats:
                    proposed_format = strategy.proposed_format
                else:
                    reason_codes.append("MODEL_FORMAT_REJECTED")
                urgency = strategy.urgency
                reason_codes.append("MODEL_STRATEGY_ENRICHED")
            except (
                BudgetExceededError,
                ModelGatewayError,
                StructuredOutputError,
            ):
                reason_codes.append("MODEL_STRATEGY_FALLBACK")

        candidate = TopicCandidate(
            workflow_run_id=workflow_run_id,
            version=1,
            cluster_key=selected_key,
            title=title,
            proposed_angle=angle,
            proposed_format=proposed_format,
            urgency=urgency.value,
            decision=decision.value,
            novelty_score=score.novelty,
            relevance_score=score.relevance,
            source_diversity_score=score.source_diversity,
            composite_score=score.composite,
            risk_class=risk_class,
            confidence_class=ConfidenceClass.C1.value,
            reason_codes=reason_codes,
            source_item_ids=[str(document.id) for document in selected],
            reason_details={
                "policy_version": policy.version,
                "input_signal_count": len(documents),
                "cluster_count": len(clusters),
                "selected_cluster_size": len(selected),
                "scores": {
                    "novelty": score.novelty,
                    "relevance": score.relevance,
                    "source_diversity": score.source_diversity,
                    "composite": score.composite,
                },
            },
        )
        with self._session_factory.begin() as session:
            session.add(candidate)
            session.flush()
            candidate_id = candidate.id

        pending_gate: str | None = None
        if decision is TopicDecision.PROPOSE:
            transition = self._workflow_engine.apply(
                workflow_run_id,
                WorkflowCommand(
                    action_key=f"topic-proposed:{candidate_id}:v1",
                    action_type=WorkflowActionType.TOPIC_PROPOSED,
                    actor_kind=AuditActorKind.AGENT,
                    actor_id=self.agent_id,
                    payload={
                        "candidate_id": str(candidate_id),
                        "candidate_version": 1,
                        "cluster_key": selected_key,
                        "decision": decision.value,
                        "composite_score": score.composite,
                    },
                ),
            )
            pending_gate = transition.pending_gate

        self._observability.record_product_event(
            ProductTelemetryEvent(
                event_name="editorial intelligence assessed",
                workflow_run_id=workflow_run_id,
                agent_id=self.agent_id,
                properties={
                    "candidate_id": str(candidate_id),
                    "decision": decision.value,
                    "composite_score": score.composite,
                    "cluster_size": len(selected),
                    "pending_gate": pending_gate,
                },
            )
        )

        with self._session_factory() as session:
            persisted = session.get(TopicCandidate, candidate_id)
            assert persisted is not None
            return self._result(persisted, pending_gate=pending_gate)

    def edit_angle(
        self,
        candidate_id: UUID,
        *,
        expected_version: int,
        proposed_angle: str,
        actor_id: str,
    ) -> EditorialIntelligenceResult:
        angle = proposed_angle.strip()
        if not angle:
            raise ValueError("proposed_angle cannot be empty.")

        with self._session_factory.begin() as session:
            candidate = session.scalar(
                select(TopicCandidate)
                .where(TopicCandidate.id == candidate_id)
                .with_for_update()
            )
            if candidate is None:
                raise EditorialIntelligenceError(f"Unknown topic candidate: {candidate_id}")
            run = session.get(WorkflowRun, candidate.workflow_run_id)
            if run is None:
                raise EditorialIntelligenceError("Candidate workflow run is missing.")
            if WorkflowStatus(run.status) is not WorkflowStatus.CANDIDATE:
                raise InvalidTransitionError(
                    "Topic angle can only be edited while Gate A is pending."
                )
            if candidate.version != expected_version:
                raise CandidateVersionConflictError(
                    f"Expected candidate version {expected_version}, got {candidate.version}."
                )

            previous_angle = candidate.proposed_angle
            candidate.proposed_angle = angle
            candidate.version += 1
            if "OPERATOR_EDITED_ANGLE" not in candidate.reason_codes:
                candidate.reason_codes = [*candidate.reason_codes, "OPERATOR_EDITED_ANGLE"]
            candidate.reason_details = {
                **candidate.reason_details,
                "last_operator_edit": {
                    "actor_id": actor_id,
                    "previous_angle": previous_angle,
                    "edited_at": utcnow().isoformat(),
                },
            }
            session.add(
                AuditEvent(
                    workflow_run_id=run.id,
                    actor_kind=AuditActorKind.HUMAN.value,
                    actor_id=actor_id,
                    event_type="topic_candidate.angle.edited",
                    entity_type="topic_candidate",
                    entity_id=candidate.id,
                    occurred_at=utcnow(),
                    payload={
                        "from_version": expected_version,
                        "to_version": candidate.version,
                    },
                )
            )
            session.flush()
            return self._result(candidate, pending_gate="A")

    def decide_gate_a(
        self,
        candidate_id: UUID,
        *,
        expected_version: int,
        actor_id: str,
        outcome: GateOutcome,
        reason: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            candidate = session.get(TopicCandidate, candidate_id)
            if candidate is None:
                raise EditorialIntelligenceError(f"Unknown topic candidate: {candidate_id}")
            if candidate.version != expected_version:
                raise CandidateVersionConflictError(
                    f"Expected candidate version {expected_version}, got {candidate.version}."
                )
            workflow_run_id = candidate.workflow_run_id

        self._workflow_engine.decide_gate(
            workflow_run_id,
            GateKind.TOPIC,
            GateResume(
                action_key=f"gate-a:{candidate_id}:v{expected_version}:{outcome.value}",
                outcome=outcome,
                actor_id=actor_id,
                artifact_type="topic_candidate",
                artifact_id=candidate_id,
                artifact_version=expected_version,
                reason=reason,
            ),
        )

    def _load_documents(
        self,
        session: Session,
        source_item_ids: list[UUID],
        *,
        policy: VerticalIntelligencePolicy,
    ) -> list[SignalDocument]:
        rows = list(
            session.execute(
                select(SourceItem, Source)
                .join(Source, Source.id == SourceItem.source_id)
                .where(SourceItem.id.in_(source_item_ids))
            )
        )
        if len(rows) != len(set(source_item_ids)):
            raise EditorialIntelligenceError("One or more source items do not exist.")

        documents: list[SignalDocument] = []
        for item, source in rows:
            if not source.enabled:
                continue
            if source.vertical_keys and policy.vertical_key not in source.vertical_keys:
                continue
            locale = item.locale or source.locale
            if policy.eligible_locales and locale not in policy.eligible_locales:
                continue
            summary_value = item.extracted_payload.get("summary", "")
            summary = summary_value if isinstance(summary_value, str) else ""
            documents.append(
                SignalDocument(
                    id=item.id,
                    source_id=item.source_id,
                    title=item.title or item.canonical_url,
                    summary=summary,
                    locale=locale,
                    published_at_iso=(
                        item.published_at.isoformat() if item.published_at is not None else None
                    ),
                    observed_at_iso=item.observed_at.isoformat(),
                )
            )
        return documents

    @staticmethod
    def _recent_topics(
        session: Session,
        *,
        run: WorkflowRun,
        policy: VerticalIntelligencePolicy,
        now: datetime,
    ) -> list[tuple[str, str]]:
        cutoff = now - timedelta(hours=policy.thresholds.novelty_window_hours)
        return list(
            session.execute(
                select(TopicCandidate.cluster_key, TopicCandidate.title)
                .join(WorkflowRun, WorkflowRun.id == TopicCandidate.workflow_run_id)
                .where(
                    WorkflowRun.vertical_key == run.vertical_key,
                    TopicCandidate.workflow_run_id != run.id,
                    TopicCandidate.created_at >= cutoff,
                )
            )
        )

    def _model_strategy(
        self,
        workflow_run_id: UUID,
        *,
        title: str,
        decision: TopicDecision,
        score: int,
        source_count: int,
        policy: VerticalIntelligencePolicy,
        call_key: str,
    ) -> EditorialStrategyOutput:
        assert self._model_gateway is not None
        request = ModelRequest(
            workflow_run_id=workflow_run_id,
            agent_id=self.agent_id,
            task=ModelTask.EDITORIAL_INTELLIGENCE,
            messages=[
                ModelMessage(
                    role=ModelRole.SYSTEM,
                    content=(
                        "You propose editorial framing only. Do not decide whether the topic "
                        "is true, do not invent facts, and do not change the deterministic "
                        "IGNORE/WATCH/PROPOSE decision."
                    ),
                ),
                ModelMessage(
                    role=ModelRole.USER,
                    content=json.dumps(
                        {
                            "title": title,
                            "decision": decision.value,
                            "deterministic_score": score,
                            "source_count": source_count,
                            "vertical": policy.vertical_key,
                            "supported_formats": policy.supported_formats,
                        },
                        sort_keys=True,
                    ),
                ),
            ],
            temperature=0,
            max_output_tokens=500,
        )
        return self._model_gateway.generate_structured(
            request,
            EditorialStrategyOutput,
            call_key=call_key,
        )

    @staticmethod
    def _default_urgency(
        documents: list[SignalDocument],
        stale: bool,
        novelty: int,
        now: datetime,
    ) -> TopicUrgency:
        if stale:
            return TopicUrgency.LOW
        newest = max(
            datetime.fromisoformat(document.published_at_iso or document.observed_at_iso)
            for document in documents
        )
        age_hours = (now - newest).total_seconds() / 3600
        if age_hours <= 6 and novelty >= 80:
            return TopicUrgency.HIGH
        return TopicUrgency.NORMAL

    @staticmethod
    def _result(
        candidate: TopicCandidate,
        *,
        pending_gate: str | None = None,
    ) -> EditorialIntelligenceResult:
        return EditorialIntelligenceResult(
            workflow_run_id=candidate.workflow_run_id,
            candidate_id=candidate.id,
            candidate_version=candidate.version,
            decision=TopicDecision(candidate.decision),
            cluster_key=candidate.cluster_key,
            source_item_ids=[UUID(value) for value in candidate.source_item_ids],
            novelty_score=candidate.novelty_score,
            relevance_score=candidate.relevance_score,
            source_diversity_score=candidate.source_diversity_score,
            composite_score=candidate.composite_score,
            proposed_angle=candidate.proposed_angle,
            proposed_format=candidate.proposed_format,
            urgency=TopicUrgency(candidate.urgency),
            reason_codes=list(candidate.reason_codes),
            pending_gate="A" if pending_gate == "A" else None,
        )
