from typing import Any

from langfuse import Langfuse

from editorial_os_api.observability.contracts import (
    EvaluationTelemetryEvent,
    ModelTelemetryEvent,
    ProductTelemetryEvent,
)
from editorial_os_api.observability.redaction import redact


class LangfuseTelemetrySink:
    """Langfuse v4 adapter using deterministic trace IDs per workflow run."""

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        base_url: str,
        environment: str,
        capture_model_io: bool = False,
        client: Any | None = None,
    ) -> None:
        self._capture_model_io = capture_model_io
        self._client: Any = client or Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            environment=environment,
        )

    def record_model_call(self, event: ModelTelemetryEvent) -> None:
        trace_id = self._trace_id(event.workflow_run_id)
        metadata = redact(
            {
                "workflow_run_id": str(event.workflow_run_id),
                "agent_id": event.agent_id,
                "task": event.task,
                "call_key": event.call_key,
                "route_name": event.route_name,
                "status": event.status,
                "cost_is_estimated": event.cost_is_estimated,
                "error_category": (
                    event.error_category.value if event.error_category is not None else None
                ),
                "error_type": event.error_type,
            }
        )
        usage_details = {
            key: value
            for key, value in {
                "input": event.input_tokens,
                "output": event.output_tokens,
                "total": (
                    (event.input_tokens or 0) + (event.output_tokens or 0)
                    if event.input_tokens is not None or event.output_tokens is not None
                    else None
                ),
            }.items()
            if value is not None
        }
        cost_details = (
            {"total": float(event.cost_usd)} if event.cost_usd is not None else None
        )

        kwargs: dict[str, Any] = {
            "trace_context": {"trace_id": trace_id},
            "name": f"model:{event.agent_id}:{event.task}",
            "as_type": "generation",
            "model": event.provider_model,
            "metadata": metadata,
            "usage_details": usage_details or None,
            "cost_details": cost_details,
            "level": "ERROR" if event.status == "failed" else "DEFAULT",
            "status_message": event.error_message,
        }
        if self._capture_model_io:
            kwargs["input"] = redact(event.model_input)
            kwargs["output"] = redact(event.model_output)

        observation = self._client.start_observation(**kwargs)
        observation.end()

    def record_evaluation(self, event: EvaluationTelemetryEvent) -> None:
        self._client.create_score(
            name=event.name,
            value=event.value,
            trace_id=self._trace_id(event.workflow_run_id),
            data_type=event.data_type,
            comment=event.comment,
        )

    def record_product_event(self, event: ProductTelemetryEvent) -> None:
        del event

    def shutdown(self) -> None:
        self._client.shutdown()

    def _trace_id(self, workflow_run_id: object) -> str:
        return str(self._client.create_trace_id(seed=str(workflow_run_id)))
