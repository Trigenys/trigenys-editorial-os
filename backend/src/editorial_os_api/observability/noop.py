from editorial_os_api.observability.contracts import (
    EvaluationTelemetryEvent,
    ModelTelemetryEvent,
    ProductTelemetryEvent,
)


class NoopTelemetrySink:
    def record_model_call(self, event: ModelTelemetryEvent) -> None:
        del event

    def record_evaluation(self, event: EvaluationTelemetryEvent) -> None:
        del event

    def record_product_event(self, event: ProductTelemetryEvent) -> None:
        del event

    def shutdown(self) -> None:
        return None
