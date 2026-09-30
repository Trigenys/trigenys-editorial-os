from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.distribution.contracts import (
    ChannelVariant,
    DistributionAdapter,
    DistributionReconciliationRequired,
    DistributionRetryableError,
    DistributionTerminalError,
    PeripheralWorkflowAdapter,
)
from editorial_os_api.distribution.copy import (
    CanonicalArticle,
    ChannelCopyGenerator,
)
from editorial_os_api.domain.enums import (
    AuditActorKind,
    DistributionStatus,
    PublicationStatus,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.orchestration.engine import PostgresWorkflowEngine
from editorial_os_api.orchestration.models import WorkflowCommand
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import (
    AuditEvent,
    DistributionJob,
    Draft,
    Publication,
    WorkflowRun,
)


class DistributionPolicyError(RuntimeError):
    pass


class DistributionService:
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

    def preview(
        self,
        publication_id: UUID,
        *,
        provider: str,
        channel: str,
        integration_id: str,
        generator: ChannelCopyGenerator | None = None,
        scheduled_at: datetime | None = None,
        settings: dict[str, object] | None = None,
    ) -> DistributionJob:
        copy_generator = generator or ChannelCopyGenerator()

        with self.session_factory.begin() as session:
            publication = session.get(Publication, publication_id)
            if publication is None:
                raise DistributionPolicyError("Publication does not exist.")
            if PublicationStatus(publication.status) is not PublicationStatus.PUBLISHED:
                raise DistributionPolicyError(
                    "Distribution preview requires a published canonical article."
                )
            if not publication.external_url:
                raise DistributionPolicyError(
                    "Published article needs a canonical external URL for distribution."
                )

            draft = session.get(Draft, publication.draft_id)
            if draft is None:
                raise DistributionPolicyError("Publication draft does not exist.")

            variant = copy_generator.generate(
                CanonicalArticle(
                    title=draft.title,
                    deck=draft.deck,
                    url=publication.external_url,
                    locale=draft.locale,
                ),
                channel=channel,
                integration_id=integration_id,
                scheduled_at=scheduled_at,
                settings=settings,
            )
            idempotency_key = self._idempotency_key(
                provider,
                publication.id,
                variant.channel,
                integration_id,
            )
            existing = session.scalar(
                select(DistributionJob).where(
                    DistributionJob.provider == provider,
                    DistributionJob.channel == variant.channel,
                    DistributionJob.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return self._detached(session, existing)

            owner_key = (
                f"editorial-os:{publication.id}:"
                f"{variant.channel}:{integration_id}"
            )
            job = DistributionJob(
                workflow_run_id=publication.workflow_run_id,
                publication_id=publication.id,
                provider=provider,
                channel=variant.channel,
                status=DistributionStatus.PREVIEW.value,
                owner_key=owner_key,
                idempotency_key=idempotency_key,
                external_id=None,
                external_url=None,
                payload=self._variant_payload(variant),
                receipt={},
            )
            session.add(job)
            session.flush()
            self._audit(
                session,
                job,
                "distribution.preview_created",
                {
                    "provider": provider,
                    "channel": variant.channel,
                    "integration_id": integration_id,
                },
            )
            return self._detached(session, job)

    def dispatch(
        self,
        distribution_job_id: UUID,
        *,
        adapter: DistributionAdapter,
    ) -> DistributionJob:
        with self.session_factory.begin() as session:
            job = session.get(DistributionJob, distribution_job_id)
            if job is None:
                raise DistributionPolicyError("Distribution job does not exist.")
            if job.provider != adapter.name:
                raise DistributionPolicyError(
                    "Adapter does not match distribution provider."
                )

            status = DistributionStatus(job.status)
            if status in {
                DistributionStatus.SCHEDULED,
                DistributionStatus.POSTED,
            }:
                return self._detached(session, job)
            if status is DistributionStatus.DISPATCHING:
                raise DistributionReconciliationRequired(
                    "Distribution is in an ambiguous dispatch state; "
                    "reconcile provider state before retrying."
                )
            if status is DistributionStatus.FAILED_TERMINAL:
                raise DistributionPolicyError(
                    "Terminally failed distribution cannot be retried."
                )

            publication = session.get(Publication, job.publication_id)
            if publication is None:
                raise DistributionPolicyError("Publication does not exist.")
            if PublicationStatus(publication.status) is not PublicationStatus.PUBLISHED:
                raise DistributionPolicyError(
                    "Canonical publication must remain published before distribution."
                )

            variant = self._variant_from_payload(job.payload)
            job.status = DistributionStatus.DISPATCHING.value
            job.receipt = {
                **job.receipt,
                "dispatch_started_at": utcnow().isoformat(),
            }
            self._audit(
                session,
                job,
                "distribution.dispatch_started",
                {
                    "provider": adapter.name,
                    "channel": job.channel,
                    "idempotency_key": job.idempotency_key,
                },
            )
            job_id = job.id
            workflow_run_id = job.workflow_run_id
            owner_key = job.owner_key
            idempotency_key = job.idempotency_key

        try:
            receipt = adapter.deliver(
                variant,
                owner_key=owner_key,
                idempotency_key=idempotency_key,
            )
        except DistributionReconciliationRequired as exc:
            self._mark_ambiguous(job_id, str(exc))
            raise
        except DistributionRetryableError as exc:
            self._mark_failure(job_id, retryable=True, message=str(exc))
            raise
        except DistributionTerminalError as exc:
            self._mark_failure(job_id, retryable=False, message=str(exc))
            raise

        try:
            remote_status = DistributionStatus(receipt.status)
        except ValueError as exc:
            self._mark_failure(
                job_id,
                retryable=False,
                message=f"Unsupported distribution status: {receipt.status}",
            )
            raise DistributionTerminalError(
                f"Unsupported distribution status: {receipt.status}"
            ) from exc

        if remote_status not in {
            DistributionStatus.SCHEDULED,
            DistributionStatus.POSTED,
        }:
            self._mark_failure(
                job_id,
                retryable=False,
                message=(
                    "Distribution receipt must be SCHEDULED or POSTED, got "
                    f"{remote_status.value}."
                ),
            )
            raise DistributionTerminalError(
                "Distribution receipt did not represent an accepted social post."
            )

        with self.session_factory.begin() as session:
            stored = session.get(DistributionJob, job_id)
            if stored is None:
                raise DistributionPolicyError(
                    "Distribution job disappeared while persisting receipt."
                )
            stored.status = remote_status.value
            stored.external_id = receipt.external_id
            stored.external_url = receipt.external_url
            stored.receipt = {
                "provider_receipt": receipt.raw,
                "scheduled_at": (
                    receipt.scheduled_at.isoformat()
                    if receipt.scheduled_at is not None
                    else None
                ),
            }
            self._audit(
                session,
                stored,
                (
                    "distribution.posted"
                    if remote_status is DistributionStatus.POSTED
                    else "distribution.scheduled"
                ),
                {
                    "provider": adapter.name,
                    "channel": stored.channel,
                    "external_id": receipt.external_id,
                },
            )

        self._advance_distribution(workflow_run_id, job_id)
        return self._job(job_id)

    def _advance_distribution(
        self,
        workflow_run_id: UUID,
        job_id: UUID,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise DistributionPolicyError("Workflow run does not exist.")
            status = WorkflowStatus(run.status)

        if status is WorkflowStatus.PUBLISHED:
            self.workflow_engine.apply(
                workflow_run_id,
                WorkflowCommand(
                    action_key=f"distribution-completed:{job_id}",
                    action_type=WorkflowActionType.DISTRIBUTION_COMPLETED,
                    actor_kind=AuditActorKind.SYSTEM,
                    actor_id="distribution-service",
                    payload={"distribution_job_id": str(job_id)},
                ),
            )
        elif status not in {
            WorkflowStatus.DISTRIBUTED,
            WorkflowStatus.MEASURED,
        }:
            raise DistributionPolicyError(
                f"Distribution cannot reconcile workflow from {status.value}."
            )

    def _mark_failure(
        self,
        job_id: UUID,
        *,
        retryable: bool,
        message: str,
    ) -> None:
        with self.session_factory.begin() as session:
            job = session.get(DistributionJob, job_id)
            if job is None:
                return
            job.status = (
                DistributionStatus.FAILED_RETRYABLE.value
                if retryable
                else DistributionStatus.FAILED_TERMINAL.value
            )
            job.receipt = {
                **job.receipt,
                "last_error": message,
                "retryable": retryable,
            }
            self._audit(
                session,
                job,
                "distribution.failed",
                {"retryable": retryable, "message": message},
            )

    def _mark_ambiguous(self, job_id: UUID, message: str) -> None:
        with self.session_factory.begin() as session:
            job = session.get(DistributionJob, job_id)
            if job is None:
                return
            job.status = DistributionStatus.DISPATCHING.value
            job.receipt = {
                **job.receipt,
                "last_error": message,
                "reconciliation_required": True,
            }
            self._audit(
                session,
                job,
                "distribution.reconciliation_required",
                {"message": message},
            )

    def _job(self, job_id: UUID) -> DistributionJob:
        with self.session_factory() as session:
            job = session.get(DistributionJob, job_id)
            if job is None:
                raise DistributionPolicyError("Distribution job does not exist.")
            return self._detached(session, job)

    @staticmethod
    def _variant_payload(variant: ChannelVariant) -> dict[str, object]:
        return {
            "channel": variant.channel,
            "integration_id": variant.integration_id,
            "content": variant.content,
            "settings": variant.settings,
            "media": list(variant.media),
            "scheduled_at": (
                variant.scheduled_at.isoformat()
                if variant.scheduled_at is not None
                else None
            ),
        }

    @staticmethod
    def _variant_from_payload(payload: dict[str, object]) -> ChannelVariant:
        channel = payload.get("channel")
        integration_id = payload.get("integration_id")
        content = payload.get("content")
        if not isinstance(channel, str):
            raise DistributionPolicyError("Distribution channel is invalid.")
        if not isinstance(integration_id, str):
            raise DistributionPolicyError("Distribution integration id is invalid.")
        if not isinstance(content, str):
            raise DistributionPolicyError("Distribution content is invalid.")

        settings_raw = payload.get("settings", {})
        if not isinstance(settings_raw, dict):
            raise DistributionPolicyError("Distribution settings are invalid.")
        settings = {
            str(key): cast(object, value)
            for key, value in settings_raw.items()
        }

        media_raw = payload.get("media", [])
        if not isinstance(media_raw, list) or not all(
            isinstance(item, str) for item in media_raw
        ):
            raise DistributionPolicyError("Distribution media is invalid.")

        scheduled_raw = payload.get("scheduled_at")
        scheduled_at = None
        if isinstance(scheduled_raw, str):
            scheduled_at = datetime.fromisoformat(
                scheduled_raw.replace("Z", "+00:00")
            )
        elif scheduled_raw is not None:
            raise DistributionPolicyError("Distribution schedule is invalid.")

        return ChannelVariant(
            channel=channel,
            integration_id=integration_id,
            content=content,
            settings=settings,
            media=tuple(cast(list[str], media_raw)),
            scheduled_at=scheduled_at,
        )

    @staticmethod
    def _idempotency_key(
        provider: str,
        publication_id: UUID,
        channel: str,
        integration_id: str,
    ) -> str:
        raw = (
            f"{provider}|{publication_id}|{channel.lower()}|{integration_id}"
        ).encode()
        return f"distribution:{sha256(raw).hexdigest()}"

    @staticmethod
    def _detached(
        session: Session,
        job: DistributionJob,
    ) -> DistributionJob:
        session.expunge(job)
        return job

    @staticmethod
    def _audit(
        session: Session,
        job: DistributionJob,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        session.add(
            AuditEvent(
                workflow_run_id=job.workflow_run_id,
                actor_kind=AuditActorKind.SYSTEM.value,
                actor_id=f"distribution:{job.provider}",
                event_type=event_type,
                entity_type="distribution_job",
                entity_id=job.id,
                occurred_at=utcnow(),
                payload=payload,
            )
        )


class PeripheralWorkflowService:
    """Audited optional hooks that cannot mutate canonical workflow state."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def trigger(
        self,
        workflow_run_id: UUID,
        *,
        adapter: PeripheralWorkflowAdapter,
        event_name: str,
        payload: dict[str, object],
        event_key: str,
    ) -> dict[str, object]:
        with self.session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise DistributionPolicyError("Workflow run does not exist.")

        receipt = adapter.trigger(
            event_name,
            payload,
            idempotency_key=event_key,
        )
        with self.session_factory.begin() as session:
            session.add(
                AuditEvent(
                    workflow_run_id=workflow_run_id,
                    actor_kind=AuditActorKind.SYSTEM.value,
                    actor_id=f"peripheral:{adapter.name}",
                    event_type="peripheral.triggered",
                    entity_type="workflow_run",
                    entity_id=workflow_run_id,
                    occurred_at=utcnow(),
                    payload={
                        "event_name": event_name,
                        "event_key": event_key,
                        "provider": adapter.name,
                        "receipt": receipt,
                    },
                )
            )
        return receipt
