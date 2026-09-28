"""Application observability that never owns canonical product state."""

from editorial_os_api.observability.context import (
    CorrelationContext,
    bind_correlation,
    current_correlation,
)
from editorial_os_api.observability.contracts import (
    ErrorCategory,
    EvaluationTelemetryEvent,
    ModelTelemetryEvent,
    ProductTelemetryEvent,
    TelemetrySink,
)
from editorial_os_api.observability.hub import ObservabilityHub
from editorial_os_api.observability.noop import NoopTelemetrySink

__all__ = [
    "CorrelationContext",
    "ErrorCategory",
    "EvaluationTelemetryEvent",
    "ModelTelemetryEvent",
    "NoopTelemetrySink",
    "ObservabilityHub",
    "ProductTelemetryEvent",
    "TelemetrySink",
    "bind_correlation",
    "current_correlation",
]
