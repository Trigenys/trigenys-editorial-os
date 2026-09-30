from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

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


def _service() -> OperatorConsoleService:
    return OperatorConsoleService(get_session_factory())


@router.get("/runs", response_model=list[OperatorRunSummary])
def list_runs(
    vertical: str | None = None,
    run_status: WorkflowStatus | None = Query(default=None, alias="status"),
    risk: str | None = None,
    topic_decision: str | None = None,
    updated_after: datetime | None = None,
    updated_before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[OperatorRunSummary]:
    return _service().list_runs(
        vertical=vertical,
        status=run_status,
        risk=risk,
        topic_decision=topic_decision,
        updated_after=updated_after,
        updated_before=updated_before,
        limit=limit,
    )


@router.get("/runs/{workflow_run_id}", response_model=OperatorRunDetail)
def run_detail(workflow_run_id: UUID) -> OperatorRunDetail:
    try:
        return _service().detail(workflow_run_id)
    except OperatorRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found.",
        ) from exc


@router.post("/runs/{workflow_run_id}/gate", response_model=OperatorRunDetail)
def decide_gate(
    workflow_run_id: UUID,
    request: GateActionRequest,
) -> OperatorRunDetail:
    try:
        return _service().decide_gate(workflow_run_id, request)
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
    request: RecoveryActionRequest,
) -> OperatorRunDetail:
    try:
        return _service().recover(workflow_run_id, request)
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
