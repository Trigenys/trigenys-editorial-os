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
        for sink in self._sinks:
            try:
                sink.record_model_call(event)
            except Exception:
                self._report_failure(sink, "record_model_call")

    def record_evaluation(self, event: EvaluationTelemetryEvent) -> None:
        for sink in self._sinks:
            try:
                sink.record_evaluation(event)
            except Exception:
                self._report_failure(sink, "record_evaluation")

    def record_product_event(self, event: ProductTelemetryEvent) -> None:
        for sink in self._sinks:
            try:
                sink.record_product_event(event)
            except Exception:
                self._report_failure(sink, "record_product_event")

    def shutdown(self) -> None:
        for sink in self._sinks:
            try:
                sink.shutdown()
            except Exception:
                self._report_failure(sink, "shutdown")

    def _report_failure(self, sink: TelemetrySink, method: str) -> None:
        log_event(
            self._logger,
            "telemetry.delivery_failed",
            level=logging.WARNING,
            properties={
                "sink": type(sink).__name__,
                "method": method,
            },
            exc_info=True,
        )
