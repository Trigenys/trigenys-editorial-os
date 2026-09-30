from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import (
    AssetRightsStatus,
    AuditActorKind,
    ConfidenceClass,
    QAFindingSeverity,
    QAOutcome,
    RiskClass,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.editorial_qa.checks import deterministic_findings
from editorial_os_api.editorial_qa.contracts import (
    EditorialQAAdapter,
    EditorialQAResult,
    QAFinding,
    QASubjectSnapshot,
)
from editorial_os_api.editorial_qa.loading import (
    QASubject,
    QASubjectLoadError,
    load_subject,
)
from editorial_os_api.editorial_qa.policy import (
    EditorialQAPolicy,
    outcome_for_findings,
)
from editorial_os_api.observability import ObservabilityHub, ProductTelemetryEvent
from editorial_os_api.orchestration import PostgresWorkflowEngine, WorkflowCommand
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import (
    AuditEvent,
    EditorialQAReview,
    WorkflowRun,
)


class EditorialQAError(RuntimeError):
    pass


class EditorialQAAgent:
    agent_id = "editorial-qa"

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        workflow_engine: PostgresWorkflowEngine | None = None,
        observability: ObservabilityHub | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._workflow_engine = workflow_engine or PostgresWorkflowEngine(
            session_factory
        )
        self._observability = observability or ObservabilityHub()

    def review(
        self,
        draft_id: UUID,
        *,
        adapter: EditorialQAAdapter | None,
        policy: EditorialQAPolicy | None = None,
        manifest_id: UUID | None = None,
    ) -> EditorialQAResult:
        selected_policy = policy or EditorialQAPolicy()
        adapter_name = adapter.name if adapter is not None else "none"

        try:
            with self._session_factory() as session:
                subject = load_subject(
                    session,
                    draft_id,
                    manifest_id=manifest_id,
                    policy=selected_policy,
                    adapter_name=adapter_name,
                )
        except QASubjectLoadError as exc:
            raise EditorialQAError(str(exc)) from exc

        if subject.existing_review_id is not None:
            self._handoff(subject.existing_review_id)
            return self._result(subject.existing_review_id)

        if subject.workflow_status is not WorkflowStatus.ASSETS_READY:
            raise EditorialQAError(
                "Editorial QA can only create a new review from ASSETS_READY."
            )

        findings = deterministic_findings(subject, selected_policy)
        findings.extend(
            self._semantic_findings(
                subject,
                adapter=adapter,
                policy=selected_policy,
            )
        )

        high_risk = subject.risk_class in selected_policy.high_risk_human_approval
        rights_review = (
            subject.rights_status is AssetRightsStatus.REVIEW_REQUIRED
        )
        human_approval_required = high_risk or rights_review

        if high_risk:
            findings.append(
                QAFinding(
                    code="HIGH_RISK_HUMAN_APPROVAL_REQUIRED",
                    severity=QAFindingSeverity.WARNING,
                    category="risk",
                    message=(
                        f"{subject.risk_class.value} content requires human "
                        "Gate B approval regardless of model confidence."
                    ),
                    policy_rule="high_risk_human_approval",
                    metadata={"risk_class": subject.risk_class.value},
                )
            )

        outcome = outcome_for_findings(findings)
        reason_codes = sorted({item.code for item in findings})
        if not reason_codes:
            reason_codes = ["QA_POLICY_SATISFIED"]

        review_id = self._persist(
            subject,
            adapter_name=adapter_name,
            policy=selected_policy,
            findings=findings,
            outcome=outcome,
            human_approval_required=human_approval_required,
            reason_codes=reason_codes,
        )
        self._record_telemetry(
            subject,
            review_id=review_id,
            outcome=outcome,
            finding_count=len(findings),
        )
        self._handoff(review_id)
        return self._result(review_id)

    @staticmethod
    def _semantic_findings(
        subject: QASubject,
        *,
        adapter: EditorialQAAdapter | None,
        policy: EditorialQAPolicy,
    ) -> list[QAFinding]:
        if not policy.require_semantic_checks:
            return []
        if adapter is None:
            return [
                QAFinding(
                    code="SEMANTIC_QA_UNAVAILABLE",
                    severity=QAFindingSeverity.ERROR,
                    category="semantic",
                    message=(
                        "Headline/body and asset/text consistency checks were not run."
                    ),
                    policy_rule="require_semantic_checks",
                )
            ]

        semantic = adapter.review(
            subject.workflow_run_id,
            draft=subject.draft,
            claims=subject.claims,
            assets=subject.assets,
            vertical_pack=subject.vertical_pack,
            call_key=f"qa:{subject.fingerprint[:48]}",
        )
        return [
            QAFinding(
                code=item.code,
                severity=QAFindingSeverity(item.severity),
                category=item.category,
                message=item.message,
                location=item.location,
                claim_id=item.claim_id,
                asset_id=item.asset_id,
                policy_rule="semantic_adapter",
            )
            for item in semantic.findings
        ]

    def _persist(
        self,
        subject: QASubject,
        *,
        adapter_name: str,
        policy: EditorialQAPolicy,
        findings: list[QAFinding],
        outcome: QAOutcome,
        human_approval_required: bool,
        reason_codes: list[str],
    ) -> UUID:
        with self._session_factory.begin() as session:
            existing = session.scalar(
                select(EditorialQAReview).where(
                    EditorialQAReview.workflow_run_id
                    == subject.workflow_run_id,
                    EditorialQAReview.draft_id == subject.draft.id,
                    EditorialQAReview.manifest_id == subject.manifest_id,
                    EditorialQAReview.input_fingerprint == subject.fingerprint,
                )
            )
            if existing is not None:
                return existing.id

            next_version = (
                session.scalar(
                    select(func.max(EditorialQAReview.version)).where(
                        EditorialQAReview.workflow_run_id
                        == subject.workflow_run_id
                    )
                )
                or 0
            ) + 1
            review = EditorialQAReview(
                workflow_run_id=subject.workflow_run_id,
                draft_id=subject.draft.id,
                manifest_id=subject.manifest_id,
                version=next_version,
                draft_version=subject.draft.version,
                manifest_version=subject.manifest_version,
                input_fingerprint=subject.fingerprint,
                outcome=outcome.value,
                confidence_class=subject.confidence_class.value,
                risk_class=subject.risk_class.value,
                human_approval_required=human_approval_required,
                gate_b_ready=outcome is QAOutcome.PASS,
                adapter_name=adapter_name,
                policy_version=policy.version,
                policy_snapshot=policy.model_dump(mode="json"),
                findings=[item.model_dump(mode="json") for item in findings],
                reason_codes=reason_codes,
                subject_snapshot=subject.snapshot.model_dump(mode="json"),
            )
            session.add(review)
            session.flush()
            session.add(
                AuditEvent(
                    workflow_run_id=subject.workflow_run_id,
                    actor_kind=AuditActorKind.AGENT.value,
                    actor_id=self.agent_id,
                    event_type="editorial.qa.completed",
                    entity_type="editorial_qa_review",
                    entity_id=review.id,
                    occurred_at=utcnow(),
                    payload={
                        "review_version": review.version,
                        "outcome": outcome.value,
                        "risk_class": subject.risk_class.value,
                        "confidence_class": subject.confidence_class.value,
                        "human_approval_required": human_approval_required,
                        "gate_b_ready": outcome is QAOutcome.PASS,
                        "reason_codes": reason_codes,
                        "subject_snapshot": subject.snapshot.model_dump(
                            mode="json"
                        ),
                    },
                )
            )
            return review.id

    def _handoff(self, review_id: UUID) -> None:
        with self._session_factory() as session:
            review = session.get(EditorialQAReview, review_id)
            if review is None:
                raise EditorialQAError("QA review no longer exists.")
            run = session.get(WorkflowRun, review.workflow_run_id)
            if run is None:
                raise EditorialQAError("QA review workflow run no longer exists.")
            status = WorkflowStatus(run.status)
            outcome = QAOutcome(review.outcome)

        if outcome is QAOutcome.PASS:
            if status in {
                WorkflowStatus.QA_PASSED,
                WorkflowStatus.EDITORIAL_APPROVED,
                WorkflowStatus.READY_TO_PUBLISH,
                WorkflowStatus.PUBLISH_APPROVED,
                WorkflowStatus.PUBLISHED,
                WorkflowStatus.DISTRIBUTED,
                WorkflowStatus.MEASURED,
            }:
                return
            action_type = WorkflowActionType.QA_PASSED
        elif outcome is QAOutcome.REVISE:
            if status is WorkflowStatus.DRAFTED:
                return
            action_type = WorkflowActionType.QA_REVISION_REQUIRED
        else:
            if status is WorkflowStatus.BLOCKED:
                return
            action_type = WorkflowActionType.BLOCK

        if status is not WorkflowStatus.ASSETS_READY:
            raise EditorialQAError(
                f"QA handoff is not legal from {status.value}."
            )

        self._workflow_engine.apply(
            review.workflow_run_id,
            WorkflowCommand(
                action_key=(
                    f"qa:{review.id}:v{review.version}:{review.outcome.lower()}"
                ),
                action_type=action_type,
                actor_kind=AuditActorKind.AGENT,
                actor_id=self.agent_id,
                payload={
                    "qa_review_id": str(review.id),
                    "qa_review_version": review.version,
                    "outcome": review.outcome,
                    "reason_codes": list(review.reason_codes),
                    "human_approval_required": review.human_approval_required,
                    "gate_b_ready": review.gate_b_ready,
                    "subject_snapshot": review.subject_snapshot,
                },
            ),
        )

    def _result(self, review_id: UUID) -> EditorialQAResult:
        with self._session_factory() as session:
            review = session.get(EditorialQAReview, review_id)
            if review is None:
                raise EditorialQAError("QA review no longer exists.")
            run = session.get(WorkflowRun, review.workflow_run_id)
            if run is None:
                raise EditorialQAError("QA review workflow run no longer exists.")
            return EditorialQAResult(
                workflow_run_id=review.workflow_run_id,
                review_id=review.id,
                review_version=review.version,
                outcome=QAOutcome(review.outcome),
                confidence_class=ConfidenceClass(review.confidence_class),
                risk_class=RiskClass(review.risk_class),
                human_approval_required=review.human_approval_required,
                gate_b_ready=review.gate_b_ready,
                findings=[
                    QAFinding.model_validate(item) for item in review.findings
                ],
                reason_codes=list(review.reason_codes),
                subject_snapshot=QASubjectSnapshot.model_validate(
                    review.subject_snapshot
                ),
                workflow_status=run.status,
            )

    def _record_telemetry(
        self,
        subject: QASubject,
        *,
        review_id: UUID,
        outcome: QAOutcome,
        finding_count: int,
    ) -> None:
        self._observability.record_product_event(
            ProductTelemetryEvent(
                event_name="editorial qa completed",
                workflow_run_id=subject.workflow_run_id,
                agent_id=self.agent_id,
                properties={
                    "review_id": str(review_id),
                    "outcome": outcome.value,
                    "finding_count": finding_count,
                    "risk_class": subject.risk_class.value,
                    "confidence_class": subject.confidence_class.value,
                },
            )
        )

