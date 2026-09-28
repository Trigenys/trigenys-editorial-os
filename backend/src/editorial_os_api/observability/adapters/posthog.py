from typing import Any

from posthog import Posthog

from editorial_os_api.observability.contracts import (
    EvaluationTelemetryEvent,
    ModelTelemetryEvent,
    ProductTelemetryEvent,
)
from editorial_os_api.observability.redaction import redact


class PostHogTelemetrySink:
    """Personless server-side analytics for workflow/editorial operations."""

    def __init__(
        self,
        *,
        project_token: str,
        host: str,
        client: Any | None = None,
    ) -> None:
        self._client: Any = client or Posthog(project_token, host=host)

    def record_model_call(self, event: ModelTelemetryEvent) -> None:
        self._capture(
            "model call recorded",
            workflow_run_id=str(event.workflow_run_id),
            properties={
                "agent_id": event.agent_id,
                "task": event.task,
                "call_key": event.call_key,
                "route_name": event.route_name,
                "provider_model": event.provider_model,
                "status": event.status,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "cost_usd": float(event.cost_usd) if event.cost_usd is not None else None,
                "cost_is_estimated": event.cost_is_estimated,
                "latency_ms": event.latency_ms,
                "error_category": (
                    event.error_category.value if event.error_category is not None else None
                ),
                "error_type": event.error_type,
            },
        )

    def record_evaluation(self, event: EvaluationTelemetryEvent) -> None:
        self._capture(
            "editorial evaluation recorded",
            workflow_run_id=str(event.workflow_run_id),
            properties={
                "name": event.name,
                "value": event.value,
                "data_type": event.data_type,
            },
        )

    def record_product_event(self, event: ProductTelemetryEvent) -> None:
        workflow_run_id = str(event.workflow_run_id) if event.workflow_run_id else None
        self._capture(
            event.event_name,
            workflow_run_id=workflow_run_id,
            properties={
                **event.properties,
                "agent_id": event.agent_id,
            },
        )

    def shutdown(self) -> None:
        self._client.shutdown()

    def _capture(
        self,
        event_name: str,
        *,
        workflow_run_id: str | None,
        properties: dict[str, object],
    ) -> None:
        distinct_id = (
            f"workflow:{workflow_run_id}" if workflow_run_id is not None else "editorial-os"
        )
        safe_properties = redact(
            {
                **properties,
                "workflow_run_id": workflow_run_id,
                "$process_person_profile": False,
            }
        )
        assert isinstance(safe_properties, dict)
        self._client.capture(
            event_name,
            distinct_id=distinct_id,
            properties=safe_properties,
        )
