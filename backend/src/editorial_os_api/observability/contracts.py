from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ErrorCategory(StrEnum):
    BUDGET = "budget"
    VALIDATION = "validation"
    PROVIDER = "provider"
    PERSISTENCE = "persistence"
    POLICY = "policy"
    TELEMETRY = "telemetry"
    INTERNAL = "internal"


class TelemetryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelTelemetryEvent(TelemetryModel):
    workflow_run_id: UUID
    agent_id: str = Field(min_length=1, max_length=120)
    task: str = Field(min_length=1, max_length=80)
    call_key: str = Field(min_length=1, max_length=255)
    route_name: str = Field(min_length=1, max_length=120)
    provider_model: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=40)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    latency_ms: int | None = Field(default=None, ge=0)
    cost_is_estimated: bool = False
    error_category: ErrorCategory | None = None
    error_type: str | None = Field(default=None, max_length=120)
    error_message: str | None = Field(default=None, max_length=500)
    model_input: object | None = None
    model_output: object | None = None


class EvaluationTelemetryEvent(TelemetryModel):
    workflow_run_id: UUID
    name: str = Field(min_length=1, max_length=120)
    value: float | str
    data_type: str = Field(min_length=1, max_length=30)
    comment: str | None = Field(default=None, max_length=500)


class ProductTelemetryEvent(TelemetryModel):
    event_name: str = Field(min_length=1, max_length=120)
    workflow_run_id: UUID | None = None
    agent_id: str | None = Field(default=None, max_length=120)
    properties: dict[str, object] = Field(default_factory=dict)


class TelemetrySink(Protocol):
    def record_model_call(self, event: ModelTelemetryEvent) -> None: ...

    def record_evaluation(self, event: EvaluationTelemetryEvent) -> None: ...

    def record_product_event(self, event: ProductTelemetryEvent) -> None: ...

    def shutdown(self) -> None: ...
