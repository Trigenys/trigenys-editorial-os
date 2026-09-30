from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import (
    AuditActorKind,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.orchestration.engine import PostgresWorkflowEngine
from editorial_os_api.orchestration.models import WorkflowCommand
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import (
    AuditEvent,
    DistributionJob,
    PerformanceSnapshot,
    Publication,
    TopicCandidate,
    WorkflowRun,
)


class PerformanceIngestionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PerformanceEvent:
    provider: str
    event_key: str
    captured_at: datetime
    metrics: dict[str, object]
    workflow_run_id: UUID | None = None
    publication_id: UUID | None = None
    distribution_job_id: UUID | None = None


class PostHogPerformanceEventParser:
    """Normalize a PostHog event/webhook payload without coupling persistence to PostHog."""

    def parse(self, payload: dict[str, object]) -> PerformanceEvent:
        properties_raw = payload.get("properties")
        if not isinstance(properties_raw, dict):
            raise PerformanceIngestionError("PostHog payload requires properties.")
        properties = {
            str(key): cast(object, value)
            for key, value in properties_raw.items()
        }

        event_key_raw = (
            payload.get("uuid")
            or properties.get("$insert_id")
            or payload.get("id")
        )
        if not isinstance(event_key_raw, (str, int)) or not str(event_key_raw):
            raise PerformanceIngestionError(
                "PostHog payload requires uuid, id or $insert_id."
            )

        captured_at = _parse_datetime(
            payload.get("timestamp") or properties.get("captured_at")
        )
        metrics_raw = properties.get("metrics")
        if isinstance(metrics_raw, dict):
            metrics = {
                str(key): cast(object, value)
                for key, value in metrics_raw.items()
            }
        else:
            metrics = {
                key: value
                for key, value in properties.items()
                if key
                not in {
                    "workflow_run_id",
                    "publication_id",
                    "distribution_job_id",
                    "$insert_id",
                    "captured_at",
                }
                and isinstance(value, (str, int, float, bool))
            }

        return PerformanceEvent(
            provider="posthog",
            event_key=str(event_key_raw),
            captured_at=captured_at,
            metrics=metrics,
            workflow_run_id=_optional_uuid(properties.get("workflow_run_id")),
            publication_id=_optional_uuid(properties.get("publication_id")),
            distribution_job_id=_optional_uuid(
                properties.get("distribution_job_id")
            ),
        )


class PerformanceService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        workflow_engine: PostgresWorkflowEngine | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.workflow_engine = workflow_engine or PostgresWorkflowEngine(
            session_factory
        )

    def ingest(self, event: PerformanceEvent) -> PerformanceSnapshot:
        with self.session_factory.begin() as session:
            (
                workflow_run_id,
                publication_id,
                distribution_job_id,
            ) = self._resolve_links(session, event)

            existing = session.scalar(
                select(PerformanceSnapshot).where(
                    PerformanceSnapshot.workflow_run_id == workflow_run_id,
                    PerformanceSnapshot.event_key == event.event_key,
                )
            )
            if existing is not None:
                return self._detached(session, existing)

            topic = session.scalar(
                select(TopicCandidate)
                .where(TopicCandidate.workflow_run_id == workflow_run_id)
                .order_by(TopicCandidate.version.desc())
                .limit(1)
            )
            snapshot = PerformanceSnapshot(
                workflow_run_id=workflow_run_id,
                topic_candidate_id=topic.id if topic is not None else None,
                publication_id=publication_id,
                distribution_job_id=distribution_job_id,
                provider=event.provider,
                event_key=event.event_key,
                captured_at=event.captured_at,
                metrics=event.metrics,
            )
            session.add(snapshot)
            session.flush()
            snapshot_id = snapshot.id

            session.add(
                AuditEvent(
                    workflow_run_id=workflow_run_id,
                    actor_kind=AuditActorKind.SYSTEM.value,
                    actor_id=f"performance:{event.provider}",
                    event_type="performance.ingested",
                    entity_type="performance_snapshot",
                    entity_id=snapshot.id,
                    occurred_at=utcnow(),
                    payload={
                        "event_key": event.event_key,
                        "provider": event.provider,
                        "publication_id": (
                            str(publication_id) if publication_id else None
                        ),
                        "distribution_job_id": (
                            str(distribution_job_id)
                            if distribution_job_id
                            else None
                        ),
                        "topic_candidate_id": (
                            str(topic.id) if topic is not None else None
                        ),
                    },
                )
            )

        self._advance_measurement(workflow_run_id, snapshot_id)
        with self.session_factory() as session:
            snapshot = session.get(PerformanceSnapshot, snapshot_id)
            if snapshot is None:
                raise PerformanceIngestionError(
                    "Performance snapshot disappeared after ingestion."
                )
            return self._detached(session, snapshot)

    @staticmethod
    def _resolve_links(
        session: Session,
        event: PerformanceEvent,
    ) -> tuple[UUID, UUID | None, UUID | None]:
        workflow_run_id = event.workflow_run_id
        publication_id = event.publication_id
        distribution_job_id = event.distribution_job_id

        distribution: DistributionJob | None = None
        if distribution_job_id is not None:
            distribution = session.get(DistributionJob, distribution_job_id)
            if distribution is None:
                raise PerformanceIngestionError(
                    "Distribution job referenced by performance event does not exist."
                )
            publication_id = publication_id or distribution.publication_id
            workflow_run_id = workflow_run_id or distribution.workflow_run_id

        publication: Publication | None = None
        if publication_id is not None:
            publication = session.get(Publication, publication_id)
            if publication is None:
                raise PerformanceIngestionError(
                    "Publication referenced by performance event does not exist."
                )
            workflow_run_id = workflow_run_id or publication.workflow_run_id

        if workflow_run_id is None:
            raise PerformanceIngestionError(
                "Performance event must map to a workflow, publication or distribution job."
            )
        run = session.get(WorkflowRun, workflow_run_id)
        if run is None:
            raise PerformanceIngestionError("Workflow run does not exist.")

        if publication is not None and publication.workflow_run_id != workflow_run_id:
            raise PerformanceIngestionError(
                "Publication does not belong to the resolved workflow."
            )
        if distribution is not None:
            if distribution.workflow_run_id != workflow_run_id:
                raise PerformanceIngestionError(
                    "Distribution job does not belong to the resolved workflow."
                )
            if (
                publication_id is not None
                and distribution.publication_id != publication_id
            ):
                raise PerformanceIngestionError(
                    "Distribution job does not belong to the resolved publication."
                )

        return workflow_run_id, publication_id, distribution_job_id

    def _advance_measurement(
        self,
        workflow_run_id: UUID,
        snapshot_id: UUID,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise PerformanceIngestionError("Workflow run does not exist.")
            status = WorkflowStatus(run.status)

        if status is WorkflowStatus.DISTRIBUTED:
            self.workflow_engine.apply(
                workflow_run_id,
                WorkflowCommand(
                    action_key=f"measurement-captured:{snapshot_id}",
                    action_type=WorkflowActionType.MEASUREMENT_CAPTURED,
                    actor_kind=AuditActorKind.SYSTEM,
                    actor_id="performance-ingestion",
                    payload={"performance_snapshot_id": str(snapshot_id)},
                ),
            )

    @staticmethod
    def _detached(
        session: Session,
        snapshot: PerformanceSnapshot,
    ) -> PerformanceSnapshot:
        session.expunge(snapshot)
        return snapshot


def _optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    if not isinstance(value, (str, UUID)):
        raise PerformanceIngestionError("Performance reference must be a UUID.")
    try:
        return value if isinstance(value, UUID) else UUID(value)
    except ValueError as exc:
        raise PerformanceIngestionError(
            "Performance reference must be a valid UUID."
        ) from exc


def _parse_datetime(value: object) -> datetime:
    if value is None:
        return utcnow()
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise PerformanceIngestionError("Performance timestamp is invalid.")
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PerformanceIngestionError(
            "Performance timestamp is not ISO-8601."
        ) from exc
