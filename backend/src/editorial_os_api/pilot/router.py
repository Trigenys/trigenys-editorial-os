from __future__ import annotations

import hashlib
import hmac
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select

from editorial_os_api.domain.enums import ConfidenceClass, WorkflowStatus
from editorial_os_api.editorial_intelligence import EditorialIntelligenceAgent
from editorial_os_api.editorial_intelligence.contracts import (
    DecisionThresholds,
    VerticalIntelligencePolicy,
)
from editorial_os_api.persistence.models import SourceItem, WorkflowRun
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.pilot.insight import (
    INSIGHT_PILOT_ID,
    INSIGHT_VERTICAL_KEY,
    INSIGHT_VERTICAL_VERSION,
    PILOT_SCENARIOS,
    seed_approved_sources,
)
from editorial_os_api.scout import ScoutAgent
from editorial_os_api.scout.adapters.manual import HttpPageExtractor
from editorial_os_api.scout.contracts import ManualUrlInput

router = APIRouter(prefix="/api/pilot", tags=["pilot"])

_TOKEN_SHA256 = "823fc4481572586f035973801b493d85ba24f9df1489fe929fc088aff8953005"


class PilotSourceInput(BaseModel):
    source_key: str = Field(min_length=1, max_length=120)
    url: HttpUrl


class PilotPrepareRequest(BaseModel):
    scenario_key: str = Field(min_length=1, max_length=120)
    sources: list[PilotSourceInput] = Field(min_length=1, max_length=6)


class PilotPrepareResponse(BaseModel):
    scenario_key: str
    workflow_run_id: UUID
    source_item_ids: list[UUID]
    candidate_id: UUID
    candidate_version: int
    candidate_decision: str
    pending_gate: str | None


def _authorize(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    token = authorization.removeprefix("Bearer ").strip()
    digest = hashlib.sha256(token.encode()).hexdigest()
    if not hmac.compare_digest(digest, _TOKEN_SHA256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@router.post("/prepare", response_model=PilotPrepareResponse)
def prepare_scenario(
    payload: PilotPrepareRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> PilotPrepareResponse:
    _authorize(authorization)

    settings = request.app.state.settings
    if settings.environment != "staging":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pilot preparation is staging-only.",
        )

    scenario = next(
        (candidate for candidate in PILOT_SCENARIOS if candidate.key == payload.scenario_key),
        None,
    )
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown scenario.")

    supplied_keys = {item.source_key for item in payload.sources}
    required_keys = set(scenario.source_keys)
    if supplied_keys != required_keys:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Source keys must match the frozen pilot scenario.",
                "required": sorted(required_keys),
                "supplied": sorted(supplied_keys),
            },
        )

    session_factory = get_session_factory(settings)
    source_ids = seed_approved_sources(session_factory)
    scout = ScoutAgent(session_factory)
    extractor = HttpPageExtractor()

    fetch_ids: list[UUID] = []
    for item in payload.sources:
        scout_result = scout.ingest_manual_url(
            source_ids[item.source_key],
            ManualUrlInput(url=item.url, locale=scenario.locale),
            extractor=extractor,
            force=True,
        )
        if scout_result.status != "SUCCEEDED" or scout_result.fetch_id is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Scout ingestion failed.",
                    "source_key": item.source_key,
                    "failure_kind": scout_result.failure_kind,
                    "retryable": scout_result.retryable,
                    "error": scout_result.error_message,
                },
            )
        fetch_ids.append(scout_result.fetch_id)

    with session_factory() as session:
        source_item_ids = list(
            session.scalars(
                select(SourceItem.id)
                .where(SourceItem.source_fetch_id.in_(fetch_ids))
                .order_by(SourceItem.observed_at.asc())
            )
        )

    if len(source_item_ids) != len(fetch_ids):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Not every successful source fetch produced a source item.",
        )

    idempotency_key = f"{INSIGHT_PILOT_ID}:{scenario.key}"
    with session_factory.begin() as session:
        run = session.scalar(
            select(WorkflowRun).where(WorkflowRun.idempotency_key == idempotency_key)
        )
        if run is None:
            run = WorkflowRun(
                vertical_key=INSIGHT_VERTICAL_KEY,
                vertical_version=INSIGHT_VERTICAL_VERSION,
                status=WorkflowStatus.INGESTED.value,
                risk_class=scenario.risk_class.value,
                confidence_class=ConfidenceClass.C0.value,
                policy_version=INSIGHT_VERTICAL_VERSION,
                idempotency_key=idempotency_key,
                context={
                    "pilot_id": INSIGHT_PILOT_ID,
                    "scenario_key": scenario.key,
                    "scenario_title": scenario.title,
                    "tags": list(scenario.tags),
                    "source_item_ids": [str(value) for value in source_item_ids],
                },
            )
            session.add(run)
            session.flush()
        elif WorkflowStatus(run.status) not in {
            WorkflowStatus.INGESTED,
            WorkflowStatus.CANDIDATE,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Scenario already advanced to {run.status}.",
            )
        workflow_run_id = run.id

    policy = VerticalIntelligencePolicy(
        vertical_key=INSIGHT_VERTICAL_KEY,
        version=INSIGHT_VERTICAL_VERSION,
        eligible_locales=[scenario.locale],
        priority_terms=list(scenario.tags),
        supported_formats=[scenario.content_format],
        default_format=scenario.content_format,
        cluster_similarity_threshold=0.05,
        thresholds=DecisionThresholds(propose_min=0, watch_min=0),
        use_model_strategy=False,
    )
    intelligence_result = EditorialIntelligenceAgent(session_factory).analyze(
        workflow_run_id,
        source_item_ids,
        policy=policy,
    )

    return PilotPrepareResponse(
        scenario_key=scenario.key,
        workflow_run_id=workflow_run_id,
        source_item_ids=source_item_ids,
        candidate_id=intelligence_result.candidate_id,
        candidate_version=intelligence_result.candidate_version,
        candidate_decision=intelligence_result.decision.value,
        pending_gate=intelligence_result.pending_gate,
    )
