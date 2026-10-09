from __future__ import annotations

from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import (
    AuditActorKind,
    GateKind,
    GateOutcome,
    RiskClass,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.orchestration.models import GateResume, WorkflowCommand, WorkflowResult
from editorial_os_api.orchestration.policy import GatePolicy
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import (
    AuditEvent,
    GateDecision,
    WorkflowAction,
    WorkflowRun,
)

TERMINAL_STATUSES = {
    WorkflowStatus.MEASURED,
    WorkflowStatus.REJECTED,
    WorkflowStatus.FAILED_TERMINAL,
}

STANDARD_TRANSITIONS: dict[WorkflowActionType, tuple[WorkflowStatus, WorkflowStatus]] = {
    WorkflowActionType.TOPIC_PROPOSED: (
        WorkflowStatus.INGESTED,
        WorkflowStatus.CANDIDATE,
    ),
    WorkflowActionType.DRAFT_COMPLETED: (
        WorkflowStatus.VERIFIED,
        WorkflowStatus.DRAFTED,
    ),
    WorkflowActionType.ASSETS_COMPLETED: (
        WorkflowStatus.DRAFTED,
        WorkflowStatus.ASSETS_READY,
    ),
    WorkflowActionType.QA_PASSED: (
        WorkflowStatus.ASSETS_READY,
        WorkflowStatus.QA_PASSED,
    ),
    WorkflowActionType.QA_REVISION_REQUIRED: (
        WorkflowStatus.ASSETS_READY,
        WorkflowStatus.DRAFTED,
    ),
    WorkflowActionType.PUBLICATION_COMPLETED: (
        WorkflowStatus.PUBLISH_APPROVED,
        WorkflowStatus.PUBLISHED,
    ),
    WorkflowActionType.DISTRIBUTION_COMPLETED: (
        WorkflowStatus.PUBLISHED,
        WorkflowStatus.DISTRIBUTED,
    ),
    WorkflowActionType.MEASUREMENT_CAPTURED: (
        WorkflowStatus.DISTRIBUTED,
        WorkflowStatus.MEASURED,
    ),
}

GATE_FOR_STATUS: dict[WorkflowStatus, GateKind] = {
    WorkflowStatus.CANDIDATE: GateKind.TOPIC,
    WorkflowStatus.QA_PASSED: GateKind.EDITORIAL,
    WorkflowStatus.READY_TO_PUBLISH: GateKind.PUBLISH,
}

APPROVED_GATE_TARGET: dict[GateKind, WorkflowStatus] = {
    GateKind.TOPIC: WorkflowStatus.TOPIC_APPROVED,
    GateKind.EDITORIAL: WorkflowStatus.EDITORIAL_APPROVED,
    GateKind.PUBLISH: WorkflowStatus.PUBLISH_APPROVED,
}

REVISION_GATE_TARGET: dict[GateKind, WorkflowStatus] = {
    GateKind.TOPIC: WorkflowStatus.CANDIDATE,
    GateKind.EDITORIAL: WorkflowStatus.DRAFTED,
    GateKind.PUBLISH: WorkflowStatus.EDITORIAL_APPROVED,
}


class WorkflowNotFoundError(LookupError):
    pass


class InvalidTransitionError(RuntimeError):
    pass


class IdempotencyConflictError(RuntimeError):
    pass


class WorkflowEngine(Protocol):
    def apply(self, workflow_run_id: UUID, command: WorkflowCommand) -> WorkflowResult: ...

    def decide_gate(
        self,
        workflow_run_id: UUID,
        gate: GateKind,
        resume: GateResume,
    ) -> WorkflowResult: ...

    def pending_gate(self, workflow_run_id: UUID) -> GateKind | None: ...

    def pending_gate_for_run(self, run: WorkflowRun) -> GateKind | None: ...


class PostgresWorkflowEngine:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        policy: GatePolicy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._policy = policy or GatePolicy()

    def apply(self, workflow_run_id: UUID, command: WorkflowCommand) -> WorkflowResult:
        if command.action_type is WorkflowActionType.GATE_DECIDED:
            raise InvalidTransitionError("Use decide_gate() for gate decisions.")

        with self._session_factory.begin() as session:
            run = self._locked_run(session, workflow_run_id)
            payload = cast(
                dict[str, object],
                command.model_dump(mode="json")["payload"],
            )

            existing = self._existing_action(session, workflow_run_id, command.action_key)
            if existing is not None:
                self._assert_same_delivery(
                    existing,
                    action_type=command.action_type,
                    actor_kind=command.actor_kind,
                    actor_id=command.actor_id,
                    payload=payload,
                )
                return self._result(run, command.action_key, applied=False)

            current = WorkflowStatus(run.status)
            target = self._target_for_command(run, command.action_type)

            from_version = run.state_version
            if command.action_type in {
                WorkflowActionType.FAILURE_RETRYABLE,
                WorkflowActionType.BLOCK,
            }:
                run.resume_status = current.value
            elif command.action_type in {
                WorkflowActionType.RETRY,
                WorkflowActionType.RESUME,
            }:
                run.resume_status = None

            run.status = target.value
            run.state_version += 1

            self._record_action(
                session,
                run=run,
                command=command,
                from_status=current,
                to_status=target,
                from_version=from_version,
                payload=payload,
            )
            self._record_audit(
                session,
                run=run,
                actor_kind=command.actor_kind,
                actor_id=command.actor_id,
                event_type=f"workflow.action.{command.action_type.value.lower()}",
                payload={
                    "action_key": command.action_key,
                    "from_status": current.value,
                    "to_status": target.value,
                    "state_version": run.state_version,
                    "payload": payload,
                },
            )
            return self._result(run, command.action_key, applied=True)

    def decide_gate(
        self,
        workflow_run_id: UUID,
        gate: GateKind,
        resume: GateResume,
    ) -> WorkflowResult:
        with self._session_factory.begin() as session:
            run = self._locked_run(session, workflow_run_id)
            current = WorkflowStatus(run.status)
            expected_gate = GATE_FOR_STATUS.get(current)

            if expected_gate is not gate:
                raise InvalidTransitionError(
                    f"Gate {gate.value} is not legal from {current.value}."
                )

            payload: dict[str, object] = {
                "gate": gate.value,
                "outcome": resume.outcome.value,
                "artifact_type": resume.artifact_type,
                "artifact_id": str(resume.artifact_id),
                "artifact_version": resume.artifact_version,
                "reason": resume.reason,
                "details": resume.details,
            }
            existing = self._existing_action(session, workflow_run_id, resume.action_key)
            if existing is not None:
                self._assert_same_delivery(
                    existing,
                    action_type=WorkflowActionType.GATE_DECIDED,
                    actor_kind=AuditActorKind.HUMAN,
                    actor_id=resume.actor_id,
                    payload=payload,
                )
                return self._result(run, resume.action_key, applied=False)

            target = self._target_for_gate(gate, resume.outcome)
            from_version = run.state_version
            run.status = target.value
            run.state_version += 1

            decision = GateDecision(
                workflow_run_id=run.id,
                gate=gate.value,
                outcome=resume.outcome.value,
                artifact_type=resume.artifact_type,
                artifact_id=resume.artifact_id,
                artifact_version=resume.artifact_version,
                actor_id=resume.actor_id,
                reason=resume.reason,
                decided_at=utcnow(),
                policy_version=run.policy_version,
                details=resume.details,
            )
            session.add(decision)

            gate_command = WorkflowCommand(
                action_key=resume.action_key,
                action_type=WorkflowActionType.GATE_DECIDED,
                actor_kind=AuditActorKind.HUMAN,
                actor_id=resume.actor_id,
                payload=payload,
            )
            self._record_action(
                session,
                run=run,
                command=gate_command,
                from_status=current,
                to_status=target,
                from_version=from_version,
                payload=payload,
            )
            self._record_audit(
                session,
                run=run,
                actor_kind=AuditActorKind.HUMAN,
                actor_id=resume.actor_id,
                event_type=f"workflow.gate.{gate.value.lower()}.{resume.outcome.value.lower()}",
                payload={
                    "action_key": resume.action_key,
                    **payload,
                    "from_status": current.value,
                    "to_status": target.value,
                    "state_version": run.state_version,
                },
            )
            return self._result(run, resume.action_key, applied=True)

    def pending_gate(self, workflow_run_id: UUID) -> GateKind | None:
        with self._session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise WorkflowNotFoundError(str(workflow_run_id))
            return self.pending_gate_for_run(run)

    def pending_gate_for_run(self, run: WorkflowRun) -> GateKind | None:
        return self._pending_gate_for_run(run)

    def _target_for_command(
        self,
        run: WorkflowRun,
        action_type: WorkflowActionType,
    ) -> WorkflowStatus:
        current = WorkflowStatus(run.status)

        if action_type is WorkflowActionType.FAILURE_TERMINAL:
            if current in TERMINAL_STATUSES:
                raise InvalidTransitionError(f"{current.value} is terminal.")
            return WorkflowStatus.FAILED_TERMINAL

        if action_type is WorkflowActionType.FAILURE_RETRYABLE:
            if current in TERMINAL_STATUSES or current in {
                WorkflowStatus.FAILED_RETRYABLE,
                WorkflowStatus.BLOCKED,
            }:
                raise InvalidTransitionError(
                    f"Retryable failure is not legal from {current.value}."
                )
            return WorkflowStatus.FAILED_RETRYABLE

        if action_type is WorkflowActionType.RETRY:
            if current is not WorkflowStatus.FAILED_RETRYABLE or run.resume_status is None:
                raise InvalidTransitionError("Retry requires FAILED_RETRYABLE with resume state.")
            return WorkflowStatus(run.resume_status)

        if action_type is WorkflowActionType.BLOCK:
            if current in TERMINAL_STATUSES or current in {
                WorkflowStatus.BLOCKED,
                WorkflowStatus.FAILED_RETRYABLE,
            }:
                raise InvalidTransitionError(f"Block is not legal from {current.value}.")
            return WorkflowStatus.BLOCKED

        if action_type is WorkflowActionType.RESUME:
            if current is not WorkflowStatus.BLOCKED or run.resume_status is None:
                raise InvalidTransitionError("Resume requires BLOCKED with resume state.")
            return WorkflowStatus(run.resume_status)

        if action_type is WorkflowActionType.VERIFICATION_COMPLETED:
            if current is WorkflowStatus.TOPIC_APPROVED:
                return WorkflowStatus.VERIFIED
            if current is WorkflowStatus.CANDIDATE and not self._gate_required(
                run,
                GateKind.TOPIC,
            ):
                return WorkflowStatus.VERIFIED
            raise InvalidTransitionError(
                f"VERIFICATION_COMPLETED is not legal from {current.value}."
            )

        if action_type is WorkflowActionType.PACKAGE_READY:
            if current is WorkflowStatus.EDITORIAL_APPROVED:
                return WorkflowStatus.READY_TO_PUBLISH
            if current is WorkflowStatus.QA_PASSED and not self._gate_required(
                run,
                GateKind.EDITORIAL,
            ):
                return WorkflowStatus.READY_TO_PUBLISH
            raise InvalidTransitionError(f"PACKAGE_READY is not legal from {current.value}.")

        transition = STANDARD_TRANSITIONS.get(action_type)
        if transition is None:
            raise InvalidTransitionError(f"Unsupported action: {action_type.value}.")

        expected, target = transition
        if current is not expected:
            raise InvalidTransitionError(
                f"{action_type.value} requires {expected.value}, got {current.value}."
            )
        return target

    @staticmethod
    def _target_for_gate(gate: GateKind, outcome: GateOutcome) -> WorkflowStatus:
        if outcome is GateOutcome.APPROVED:
            return APPROVED_GATE_TARGET[gate]
        if outcome is GateOutcome.REJECTED:
            return WorkflowStatus.REJECTED
        if outcome is GateOutcome.REVISION_REQUESTED:
            return REVISION_GATE_TARGET[gate]
        if outcome is GateOutcome.WATCH and gate is GateKind.TOPIC:
            return WorkflowStatus.CANDIDATE
        raise InvalidTransitionError(
            f"Outcome {outcome.value} is not legal for Gate {gate.value}."
        )

    def _gate_required(self, run: WorkflowRun, gate: GateKind) -> bool:
        return self._policy.is_required(
            gate,
            vertical_key=run.vertical_key,
            risk_class=RiskClass(run.risk_class),
        )

    def _pending_gate_for_run(self, run: WorkflowRun) -> GateKind | None:
        gate = GATE_FOR_STATUS.get(WorkflowStatus(run.status))
        if gate is None:
            return None
        return gate if self._gate_required(run, gate) else None

    @staticmethod
    def _locked_run(session: Session, workflow_run_id: UUID) -> WorkflowRun:
        run = session.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.id == workflow_run_id)
            .with_for_update()
        )
        if run is None:
            raise WorkflowNotFoundError(str(workflow_run_id))
        return run

    @staticmethod
    def _existing_action(
        session: Session,
        workflow_run_id: UUID,
        action_key: str,
    ) -> WorkflowAction | None:
        return session.scalar(
            select(WorkflowAction).where(
                WorkflowAction.workflow_run_id == workflow_run_id,
                WorkflowAction.action_key == action_key,
            )
        )

    @staticmethod
    def _assert_same_delivery(
        existing: WorkflowAction,
        *,
        action_type: WorkflowActionType,
        actor_kind: AuditActorKind,
        actor_id: str,
        payload: dict[str, object],
    ) -> None:
        if (
            existing.action_type != action_type.value
            or existing.actor_kind != actor_kind.value
            or existing.actor_id != actor_id
            or existing.payload != payload
        ):
            raise IdempotencyConflictError(
                f"Action key {existing.action_key!r} was reused with different content."
            )

    @staticmethod
    def _record_action(
        session: Session,
        *,
        run: WorkflowRun,
        command: WorkflowCommand,
        from_status: WorkflowStatus,
        to_status: WorkflowStatus,
        from_version: int,
        payload: dict[str, object],
    ) -> None:
        session.add(
            WorkflowAction(
                workflow_run_id=run.id,
                action_key=command.action_key,
                action_type=command.action_type.value,
                actor_kind=command.actor_kind.value,
                actor_id=command.actor_id,
                from_status=from_status.value,
                to_status=to_status.value,
                from_state_version=from_version,
                to_state_version=run.state_version,
                payload=payload,
            )
        )

    @staticmethod
    def _record_audit(
        session: Session,
        *,
        run: WorkflowRun,
        actor_kind: AuditActorKind,
        actor_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        session.add(
            AuditEvent(
                workflow_run_id=run.id,
                actor_kind=actor_kind.value,
                actor_id=actor_id,
                event_type=event_type,
                entity_type="workflow_run",
                entity_id=run.id,
                occurred_at=utcnow(),
                payload=payload,
            )
        )

    def _result(
        self,
        run: WorkflowRun,
        action_key: str,
        *,
        applied: bool,
    ) -> WorkflowResult:
        pending_gate = self._pending_gate_for_run(run)
        return WorkflowResult(
            workflow_run_id=run.id,
            applied=applied,
            status=WorkflowStatus(run.status),
            state_version=run.state_version,
            action_key=action_key,
            pending_gate=pending_gate.value if pending_gate is not None else None,
        )
