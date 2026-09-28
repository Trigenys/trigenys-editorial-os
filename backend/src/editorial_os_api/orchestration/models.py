from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from editorial_os_api.domain.enums import (
    AuditActorKind,
    GateOutcome,
    WorkflowActionType,
    WorkflowStatus,
)


class OrchestrationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowCommand(OrchestrationModel):
    action_key: str = Field(min_length=1, max_length=255)
    action_type: WorkflowActionType
    actor_kind: AuditActorKind = AuditActorKind.SYSTEM
    actor_id: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)


class GateResume(OrchestrationModel):
    action_key: str = Field(min_length=1, max_length=255)
    outcome: GateOutcome
    actor_id: str = Field(min_length=1, max_length=255)
    artifact_type: str = Field(min_length=1, max_length=80)
    artifact_id: UUID
    artifact_version: int = Field(ge=1)
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class WorkflowResult(OrchestrationModel):
    workflow_run_id: UUID
    applied: bool
    status: WorkflowStatus
    state_version: int
    action_key: str
    pending_gate: str | None = None
