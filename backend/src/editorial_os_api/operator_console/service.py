from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import (
    AuditActorKind,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.operator_console.models import (
    GateActionRequest,
    GateArtifact,
    OperatorAsset,
    OperatorClaim,
    OperatorDistribution,
    OperatorDraft,
    OperatorEvidence,
    OperatorGateDecision,
    OperatorPublication,
    OperatorRunDetail,
    OperatorRunSummary,
    OperatorTimelineEvent,
    OperatorUsageSummary,
    RecoveryActionRequest,
)
from editorial_os_api.orchestration.engine import (
    InvalidTransitionError,
    PostgresWorkflowEngine,
    WorkflowNotFoundError,
)
from editorial_os_api.orchestration.models import GateResume, WorkflowCommand
from editorial_os_api.persistence.models import (
    Asset,
    AssetManifest,
    Claim,
    DistributionJob,
    Draft,
    EvidenceItem,
    GateDecision,
    ModelUsageRecord,
    Publication,
    Source,
    SourceItem,
    TopicCandidate,
    WorkflowAction,
    WorkflowRun,
)


class OperatorConsoleError(RuntimeError):
    pass


class OperatorRunNotFoundError(OperatorConsoleError):
    pass


class OperatorConsoleService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        workflow_engine: PostgresWorkflowEngine | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.workflow_engine = workflow_engine or PostgresWorkflowEngine(
            session_factory
        )

    def list_runs(
        self,
        *,
        vertical: str | None = None,
        status: WorkflowStatus | None = None,
        risk: str | None = None,
        topic_decision: str | None = None,
        updated_after: datetime | None = None,
        updated_before: datetime | None = None,
        limit: int = 50,
    ) -> list[OperatorRunSummary]:
        with self.session_factory() as session:
            statement = select(WorkflowRun).order_by(WorkflowRun.updated_at.desc())
            if vertical:
                statement = statement.where(WorkflowRun.vertical_key == vertical)
            if status is not None:
                statement = statement.where(WorkflowRun.status == status.value)
            if risk:
                statement = statement.where(WorkflowRun.risk_class == risk)
            if updated_after is not None:
                statement = statement.where(WorkflowRun.updated_at >= updated_after)
            if updated_before is not None:
                statement = statement.where(WorkflowRun.updated_at <= updated_before)
            if topic_decision:
                statement = statement.where(
                    WorkflowRun.id.in_(
                        select(TopicCandidate.workflow_run_id).where(
                            TopicCandidate.decision == topic_decision.upper()
                        )
                    )
                )

            runs = list(session.scalars(statement.limit(limit)))
            summaries: list[OperatorRunSummary] = []
            for run in runs:
                topic = self._latest_topic(session, run.id)
                summaries.append(self._summary(run, topic))
            return summaries

    def detail(self, workflow_run_id: UUID) -> OperatorRunDetail:
        with self.session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise OperatorRunNotFoundError(str(workflow_run_id))

            topic = self._latest_topic(session, run.id)
            draft = session.scalar(
                select(Draft)
                .where(Draft.workflow_run_id == run.id)
                .order_by(Draft.version.desc(), Draft.updated_at.desc())
                .limit(1)
            )
            manifest = None
            if draft is not None:
                manifest = session.scalar(
                    select(AssetManifest)
                    .where(AssetManifest.draft_id == draft.id)
                    .order_by(AssetManifest.version.desc())
                    .limit(1)
                )

            assets_statement = select(Asset).where(Asset.workflow_run_id == run.id)
            if manifest is not None:
                assets_statement = assets_statement.where(
                    Asset.manifest_id == manifest.id
                )
            assets = list(
                session.scalars(
                    assets_statement.order_by(Asset.slot, Asset.version.desc())
                )
            )
            claims = list(
                session.scalars(
                    select(Claim)
                    .where(Claim.workflow_run_id == run.id)
                    .order_by(Claim.created_at.asc())
                )
            )
            evidence = list(
                session.scalars(
                    select(EvidenceItem)
                    .where(EvidenceItem.workflow_run_id == run.id)
                    .order_by(EvidenceItem.observed_at.desc())
                )
            )
            gates = list(
                session.scalars(
                    select(GateDecision)
                    .where(GateDecision.workflow_run_id == run.id)
                    .order_by(GateDecision.decided_at.desc())
                )
            )
            timeline = list(
                session.scalars(
                    select(WorkflowAction)
                    .where(WorkflowAction.workflow_run_id == run.id)
                    .order_by(WorkflowAction.created_at.asc())
                )
            )
            usage = list(
                session.scalars(
                    select(ModelUsageRecord)
                    .where(ModelUsageRecord.workflow_run_id == run.id)
                    .order_by(ModelUsageRecord.created_at.asc())
                )
            )
            publication = session.scalar(
                select(Publication)
                .where(Publication.workflow_run_id == run.id)
                .order_by(Publication.updated_at.desc())
                .limit(1)
            )
            distributions = list(
                session.scalars(
                    select(DistributionJob)
                    .where(DistributionJob.workflow_run_id == run.id)
                    .order_by(DistributionJob.updated_at.desc())
                )
            )

            return OperatorRunDetail(
                run=self._summary(run, topic),
                gate_artifact=self._gate_artifact(
                    session,
                    run,
                    topic=topic,
                    draft=draft,
                    publication=publication,
                ),
                claims=[
                    OperatorClaim(
                        id=item.id,
                        statement=item.statement,
                        material=item.material,
                        confidence_class=item.confidence_class,
                        risk_class=item.risk_class,
                        support_status=item.support_status,
                        stale=item.stale,
                        contested=item.contested,
                    )
                    for item in claims
                ],
                evidence=[
                    OperatorEvidence(
                        id=item.id,
                        url=item.url,
                        excerpt=item.excerpt,
                        tier=item.tier,
                        source_role=item.source_role,
                        stale=item.stale,
                        observed_at=item.observed_at,
                    )
                    for item in evidence
                ],
                draft=(
                    OperatorDraft(
                        id=draft.id,
                        version=draft.version,
                        locale=draft.locale,
                        title=draft.title,
                        deck=draft.deck,
                        body=draft.body,
                        unsupported_factual_claims=draft.unsupported_factual_claims,
                    )
                    if draft is not None
                    else None
                ),
                assets=[
                    OperatorAsset(
                        id=item.id,
                        version=item.version,
                        slot=item.slot,
                        kind=item.kind,
                        uri=item.uri,
                        filename=item.filename,
                        rights_status=item.rights_status,
                        alt_text=item.alt_text,
                        caption=item.caption,
                    )
                    for item in assets
                ],
                gates=[
                    OperatorGateDecision(
                        id=item.id,
                        gate=item.gate,
                        outcome=item.outcome,
                        artifact_type=item.artifact_type,
                        artifact_id=item.artifact_id,
                        artifact_version=item.artifact_version,
                        actor_id=item.actor_id,
                        reason=item.reason,
                        decided_at=item.decided_at,
                    )
                    for item in gates
                ],
                timeline=[
                    OperatorTimelineEvent(
                        id=item.id,
                        action_key=item.action_key,
                        action_type=item.action_type,
                        actor_kind=item.actor_kind,
                        actor_id=item.actor_id,
                        from_status=item.from_status,
                        to_status=item.to_status,
                        from_state_version=item.from_state_version,
                        to_state_version=item.to_state_version,
                        created_at=item.created_at,
                    )
                    for item in timeline
                ],
                usage=self._usage_summary(usage),
                publication=(
                    OperatorPublication(
                        id=publication.id,
                        provider=publication.provider,
                        target=publication.target,
                        status=publication.status,
                        external_url=publication.external_url,
                        scheduled_at=publication.scheduled_at,
                        published_at=publication.published_at,
                    )
                    if publication is not None
                    else None
                ),
                distributions=[
                    OperatorDistribution(
                        id=item.id,
                        provider=item.provider,
                        channel=item.channel,
                        status=item.status,
                        external_url=item.external_url,
                        created_at=item.created_at,
                        updated_at=item.updated_at,
                    )
                    for item in distributions
                ],
                recovery_action=self._recovery_action(run),
            )

    def decide_gate(
        self,
        workflow_run_id: UUID,
        request: GateActionRequest,
    ) -> OperatorRunDetail:
        with self.session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise OperatorRunNotFoundError(str(workflow_run_id))
            state_version = run.state_version
            pending_gate = self.workflow_engine.pending_gate(workflow_run_id)
            if pending_gate is None:
                raise OperatorConsoleError(
                    "This run has no gate awaiting an operator decision."
                )
            artifact = self._gate_artifact(session, run)
            if artifact is None:
                raise OperatorConsoleError(
                    "The canonical artifact required by the pending gate does not exist."
                )

        action_key = (
            f"operator-gate:{workflow_run_id}:v{state_version}:"
            f"{pending_gate.value}:{artifact.artifact_id}:{request.outcome.value}"
        )
        try:
            self.workflow_engine.decide_gate(
                workflow_run_id,
                pending_gate,
                GateResume(
                    action_key=action_key,
                    outcome=request.outcome,
                    actor_id=request.actor_id,
                    artifact_type=artifact.artifact_type,
                    artifact_id=artifact.artifact_id,
                    artifact_version=artifact.artifact_version,
                    reason=request.reason,
                    details={
                        **request.details,
                        "surface": "operator-console",
                    },
                ),
            )
        except (InvalidTransitionError, WorkflowNotFoundError) as exc:
            raise OperatorConsoleError(str(exc)) from exc
        return self.detail(workflow_run_id)

    def recover(
        self,
        workflow_run_id: UUID,
        request: RecoveryActionRequest,
    ) -> OperatorRunDetail:
        with self.session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise OperatorRunNotFoundError(str(workflow_run_id))
            current = WorkflowStatus(run.status)
            state_version = run.state_version

        if current is WorkflowStatus.FAILED_RETRYABLE:
            action_type = WorkflowActionType.RETRY
        elif current is WorkflowStatus.BLOCKED:
            action_type = WorkflowActionType.RESUME
        else:
            raise OperatorConsoleError(
                f"Recovery is not legal from {current.value}."
            )

        try:
            self.workflow_engine.apply(
                workflow_run_id,
                WorkflowCommand(
                    action_key=(
                        f"operator-recovery:{workflow_run_id}:"
                        f"v{state_version}:{action_type.value}"
                    ),
                    action_type=action_type,
                    actor_kind=AuditActorKind.HUMAN,
                    actor_id=request.actor_id,
                    payload={
                        "reason": request.reason,
                        "surface": "operator-console",
                    },
                ),
            )
        except (InvalidTransitionError, WorkflowNotFoundError) as exc:
            raise OperatorConsoleError(str(exc)) from exc
        return self.detail(workflow_run_id)

    def _summary(
        self,
        run: WorkflowRun,
        topic: TopicCandidate | None,
    ) -> OperatorRunSummary:
        pending_gate = self.workflow_engine.pending_gate(run.id)
        return OperatorRunSummary(
            id=run.id,
            vertical_key=run.vertical_key,
            status=WorkflowStatus(run.status),
            risk_class=run.risk_class,
            confidence_class=run.confidence_class,
            state_version=run.state_version,
            topic_title=topic.title if topic is not None else None,
            topic_decision=topic.decision if topic is not None else None,
            topic_urgency=topic.urgency if topic is not None else None,
            pending_gate=pending_gate.value if pending_gate is not None else None,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    @staticmethod
    def _latest_topic(
        session: Session,
        workflow_run_id: UUID,
    ) -> TopicCandidate | None:
        return session.scalar(
            select(TopicCandidate)
            .where(TopicCandidate.workflow_run_id == workflow_run_id)
            .order_by(TopicCandidate.version.desc(), TopicCandidate.updated_at.desc())
            .limit(1)
        )

    def _gate_artifact(
        self,
        session: Session,
        run: WorkflowRun,
        *,
        topic: TopicCandidate | None = None,
        draft: Draft | None = None,
        publication: Publication | None = None,
    ) -> GateArtifact | None:
        status = WorkflowStatus(run.status)
        if status is WorkflowStatus.CANDIDATE:
            topic = topic or self._latest_topic(session, run.id)
            if topic is None:
                return None
            return GateArtifact(
                artifact_type="topic_candidate",
                artifact_id=topic.id,
                artifact_version=topic.version,
            )

        if status is WorkflowStatus.QA_PASSED:
            draft = draft or session.scalar(
                select(Draft)
                .where(Draft.workflow_run_id == run.id)
                .order_by(Draft.version.desc(), Draft.updated_at.desc())
                .limit(1)
            )
            if draft is None:
                return None
            return GateArtifact(
                artifact_type="draft",
                artifact_id=draft.id,
                artifact_version=draft.version,
            )

        if status is WorkflowStatus.READY_TO_PUBLISH:
            publication = publication or session.scalar(
                select(Publication)
                .where(Publication.workflow_run_id == run.id)
                .order_by(Publication.updated_at.desc())
                .limit(1)
            )
            if publication is None:
                return None
            return GateArtifact(
                artifact_type="publication",
                artifact_id=publication.id,
                artifact_version=1,
            )

        return None

    @staticmethod
    def _usage_summary(
        records: list[ModelUsageRecord],
    ) -> OperatorUsageSummary:
        actual_cost = Decimal("0")
        input_tokens = 0
        output_tokens = 0
        latencies: list[int] = []

        for item in records:
            actual_cost += item.actual_cost_usd or item.reserved_cost_usd
            input_tokens += item.input_tokens or 0
            output_tokens += item.output_tokens or 0
            if item.latency_ms is not None:
                latencies.append(item.latency_ms)

        average_latency = (
            sum(latencies) / len(latencies)
            if latencies
            else None
        )
        return OperatorUsageSummary(
            calls=len(records),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_cost_usd=actual_cost,
            average_latency_ms=average_latency,
        )

    @staticmethod
    def _recovery_action(
        run: WorkflowRun,
    ) -> Literal["RETRY", "RESUME"] | None:
        status = WorkflowStatus(run.status)
        if status is WorkflowStatus.FAILED_RETRYABLE:
            return "RETRY"
        if status is WorkflowStatus.BLOCKED:
            return "RESUME"
        return None
