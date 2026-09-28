import logging

from editorial_os_api.observability.contracts import (
    EvaluationTelemetryEvent,
    ModelTelemetryEvent,
    ProductTelemetryEvent,
    TelemetrySink,
)
from editorial_os_api.observability.logging import log_event


class ObservabilityHub:
    """Best-effort telemetry fan-out; failures never affect canonical workflow state."""

    def __init__(self, sinks: tuple[TelemetrySink, ...] = ()) -> None:
        self._sinks = sinks
        self._logger = logging.getLogger("editorial_os.observability")

    def record_model_call(self, event: ModelTelemetryEvent) -> None:
        self._fan_out("record_model_call", event)

    def record_evaluation(self, event: EvaluationTelemetryEvent) -> None:
        self._fan_out("record_evaluation", event)

    def record_product_event(self, event: ProductTelemetryEvent) -> None:
        self._fan_out("record_product_event", event)

    def shutdown(self) -> None:
        for sink in self._sinks:
            try:
                sink.shutdown()
            except Exception:
                log_event(
                    self._logger,
                    "telemetry.shutdown_failed",
                    level=logging.WARNING,
                    properties={"sink": type(sink).__name__},
                    exc_info=True,
                )

    def _fan_out(self, method_name: str, event: object) -> None:
        for sink in self._sinks:
            try:
                method = getattr(sink, method_name)
                method(event)
            except Exception:
                log_event(
                    self._logger,
                    "telemetry.delivery_failed",
                    level=logging.WARNING,
                    properties={
                        "sink": type(sink).__name__,
                        "method": method_name,
                    },
                    exc_info=True,
                )
