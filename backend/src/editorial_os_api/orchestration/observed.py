from uuid import UUID

from editorial_os_api.domain.enums import GateKind
from editorial_os_api.observability import (
    ObservabilityHub,
    ProductTelemetryEvent,
    bind_correlation,
)
from editorial_os_api.observability.errors import classify_exception
from editorial_os_api.orchestration.engine import WorkflowEngine
from editorial_os_api.orchestration.models import GateResume, WorkflowCommand, WorkflowResult


class ObservedWorkflowEngine:
    """Decorates the canonical engine without moving workflow truth into telemetry."""

    def __init__(self, delegate: WorkflowEngine, observability: ObservabilityHub) -> None:
        self._delegate = delegate
        self._observability = observability

    def apply(self, workflow_run_id: UUID, command: WorkflowCommand) -> WorkflowResult:
        with bind_correlation(
            workflow_run_id=workflow_run_id,
            call_key=command.action_key,
        ):
            try:
                result = self._delegate.apply(workflow_run_id, command)
            except Exception as exc:
                self._observability.record_product_event(
                    ProductTelemetryEvent(
                        event_name="workflow transition failed",
                        workflow_run_id=workflow_run_id,
                        properties={
                            "action_type": command.action_type.value,
                            "action_key": command.action_key,
                            "error_category": classify_exception(exc).value,
                            "error_type": type(exc).__name__,
                        },
                    )
                )
                raise

            self._observability.record_product_event(
                ProductTelemetryEvent(
                    event_name="workflow transitioned",
                    workflow_run_id=workflow_run_id,
                    properties={
                        "action_type": command.action_type.value,
                        "action_key": command.action_key,
                        "applied": result.applied,
                        "status": result.status.value,
                        "state_version": result.state_version,
                        "pending_gate": result.pending_gate,
                    },
                )
            )
            return result

    def decide_gate(
        self,
        workflow_run_id: UUID,
        gate: GateKind,
        resume: GateResume,
    ) -> WorkflowResult:
        with bind_correlation(
            workflow_run_id=workflow_run_id,
            call_key=resume.action_key,
        ):
            result = self._delegate.decide_gate(workflow_run_id, gate, resume)
            self._observability.record_product_event(
                ProductTelemetryEvent(
                    event_name="workflow gate decided",
                    workflow_run_id=workflow_run_id,
                    properties={
                        "gate": gate.value,
                        "outcome": resume.outcome.value,
                        "action_key": resume.action_key,
                        "status": result.status.value,
                        "state_version": result.state_version,
                    },
                )
            )
            return result

    def pending_gate(self, workflow_run_id: UUID) -> GateKind | None:
        with bind_correlation(workflow_run_id=workflow_run_id):
            return self._delegate.pending_gate(workflow_run_id)
