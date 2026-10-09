from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from editorial_os_api.domain.enums import WorkflowStatus
from editorial_os_api.operator_console.models import (
    GateActionRequest,
    OperatorRunDetail,
    OperatorRunSummary,
    RecoveryActionRequest,
)
from editorial_os_api.operator_console.service import (
    OperatorConsoleError,
    OperatorConsoleService,
    OperatorRunNotFoundError,
)
from editorial_os_api.persistence.session import get_session_factory

router = APIRouter(prefix="/api/operator", tags=["operator"])


def _service(request: Request) -> OperatorConsoleService:
    return OperatorConsoleService(get_session_factory(request.app.state.settings))


@router.get("/runs", response_model=list[OperatorRunSummary])
def list_runs(
    request: Request,
    vertical: str | None = None,
    run_status: Annotated[WorkflowStatus | None, Query(alias="status")] = None,
    risk: str | None = None,
    topic_decision: str | None = None,
    updated_after: datetime | None = None,
    updated_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[OperatorRunSummary]:
    return _service(request).list_runs(
        vertical=vertical,
        status=run_status,
        risk=risk,
        topic_decision=topic_decision,
        updated_after=updated_after,
        updated_before=updated_before,
        limit=limit,
    )


@router.get("/runs/{workflow_run_id}", response_model=OperatorRunDetail)
def run_detail(workflow_run_id: UUID, request: Request) -> OperatorRunDetail:
    try:
        return _service(request).detail(workflow_run_id)
    except OperatorRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found.",
        ) from exc


@router.post("/runs/{workflow_run_id}/gate", response_model=OperatorRunDetail)
def decide_gate(
    workflow_run_id: UUID,
    action: GateActionRequest,
    request: Request,
) -> OperatorRunDetail:
    try:
        return _service(request).decide_gate(workflow_run_id, action)
    except OperatorRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found.",
        ) from exc
    except OperatorConsoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post("/runs/{workflow_run_id}/recover", response_model=OperatorRunDetail)
def recover_run(
    workflow_run_id: UUID,
    action: RecoveryActionRequest,
    request: Request,
) -> OperatorRunDetail:
    try:
        return _service(request).recover(workflow_run_id, action)
    except OperatorRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found.",
        ) from exc
    except OperatorConsoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
