from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ModelTask(StrEnum):
    EDITORIAL_INTELLIGENCE = "editorial_intelligence"
    RESEARCH_VERIFICATION = "research_verification"
    CONTENT_DRAFTING = "content_drafting"
    CREATIVE_BRIEF = "creative_brief"
    EDITORIAL_QA = "editorial_qa"
    GROWTH_ANALYSIS = "growth_analysis"


class ModelRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class GatewayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelMessage(GatewayModel):
    role: ModelRole
    content: str


class ModelRoute(GatewayModel):
    name: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=255)
    max_call_cost_usd: Decimal = Field(gt=Decimal("0"))
    supports_json_mode: bool = True
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    max_retries: int = Field(default=0, ge=0, le=3)


class ModelPolicy(GatewayModel):
    routes: dict[ModelTask, ModelRoute]

    def route_for(self, task: ModelTask) -> ModelRoute:
        try:
            return self.routes[task]
        except KeyError as exc:
            raise KeyError(f"No model route configured for task {task.value!r}.") from exc


class BudgetPolicy(GatewayModel):
    per_run_usd: Decimal = Field(gt=Decimal("0"))
    default_per_agent_usd: Decimal = Field(gt=Decimal("0"))
    per_agent_usd: dict[str, Decimal] = Field(default_factory=dict)

    def ceiling_for_agent(self, agent_id: str) -> Decimal:
        return self.per_agent_usd.get(agent_id, self.default_per_agent_usd)


class ModelRequest(GatewayModel):
    workflow_run_id: UUID
    agent_id: str = Field(min_length=1, max_length=120)
    task: ModelTask
    messages: list[ModelMessage] = Field(min_length=1)
    max_output_tokens: int = Field(default=2000, ge=1, le=100_000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class RawModelResponse(GatewayModel):
    content: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    latency_ms: int = Field(ge=0)


class ModelClient(Protocol):
    def complete(
        self,
        request: ModelRequest,
        route: ModelRoute,
        *,
        json_schema: dict[str, object] | None = None,
    ) -> RawModelResponse: ...
