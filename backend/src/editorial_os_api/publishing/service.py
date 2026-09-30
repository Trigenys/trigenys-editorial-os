from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import (
    AuditActorKind,
    GateKind,
    GateOutcome,
    PublicationStatus,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.orchestration.engine import PostgresWorkflowEngine
from editorial_os_api.orchestration.models import WorkflowCommand
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import (
    Asset,
    AssetManifest,
    AuditEvent,
    Draft,
    GateDecision,
    Publication,
    WorkflowRun,
)
from editorial_os_api.publishing.contracts import (
    CMSAdapter,
    CMSAsset,
    CMSDocument,
    CMSRetryableError,
    CMSTerminalError,
)


class PublicationPolicyError(RuntimeError):
    pass


class PublishingService:
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

    def ensure_cms_draft(
        self,
        draft_id: UUID,
        *,
        adapter: CMSAdapter,
        target: str,
    ) -> Publication:
        with self.session_factory.begin() as session:
            draft = session.get(Draft, draft_id)
            if draft is None:
                raise PublicationPolicyError("Draft does not exist.")
            run = session.get(WorkflowRun, draft.workflow_run_id)
            if run is None:
                raise PublicationPolicyError("Workflow run does not exist.")

            status = WorkflowStatus(run.status)
            if status not in {
                WorkflowStatus.EDITORIAL_APPROVED,
                WorkflowStatus.READY_TO_PUBLISH,
                WorkflowStatus.PUBLISH_APPROVED,
                WorkflowStatus.PUBLISHED,
            }:
                raise PublicationPolicyError(
                    "CMS draft creation requires editorial approval first."
                )

            idempotency_key = self._idempotency_key(
                adapter.name,
                target,
                draft.id,
                draft.version,
            )
            owner_key = (
                f"editorial-os:{adapter.name}:{target}:"
                f"{run.id}:{draft.locale}"
            )
            publication = session.scalar(
                select(Publication).where(
                    Publication.provider == adapter.name,
                    Publication.target == target,
                    Publication.idempotency_key == idempotency_key,
                )
            )
            if publication is None:
                publication = Publication(
                    workflow_run_id=run.id,
                    draft_id=draft.id,
                    provider=adapter.name,
                    target=target,
                    status=PublicationStatus.DRAFT.value,
                    owner_key=owner_key,
                    idempotency_key=idempotency_key,
                    external_id=None,
                    external_url=None,
                    scheduled_at=None,
                    published_at=None,
                    receipt={},
                )
                session.add(publication)
                session.flush()

            publication_id = publication.id
            workflow_run_id = run.id
            draft_version = draft.version
            existing_external_id = publication.external_id
            existing_status = PublicationStatus(publication.status)
            document = self._build_document(session, draft)

        if existing_status is PublicationStatus.PUBLISHED:
            self._advance_publication_completed(
                workflow_run_id,
                publication_id,
                adapter_name=adapter.name,
            )
            return self._publication(publication_id)

        if (
            existing_status is PublicationStatus.DRAFT
            and existing_external_id is not None
        ):
            self._advance_package_ready(
                workflow_run_id,
                publication_id,
                draft_id=draft_id,
                draft_version=draft_version,
                adapter_name=adapter.name,
                target=target,
            )
            return self._publication(publication_id)

        try:
            receipt = adapter.upsert_draft(
                document,
                target=target,
                owner_key=owner_key,
                idempotency_key=idempotency_key,
                existing_external_id=existing_external_id,
            )
        except CMSRetryableError as exc:
            self._mark_failure(
                publication_id,
                retryable=True,
                message=str(exc),
            )
            raise
        except CMSTerminalError as exc:
            self._mark_failure(
                publication_id,
                retryable=False,
                message=str(exc),
            )
            raise

        with self.session_factory.begin() as session:
            stored = session.get(Publication, publication_id)
            if stored is None:
                raise PublicationPolicyError(
                    "Publication disappeared during CMS reconciliation."
                )
            stored.status = PublicationStatus.DRAFT.value
            stored.external_id = receipt.external_id
            stored.external_url = receipt.external_url
            stored.receipt = {
                "phase": "draft",
                "adapter": adapter.name,
                "provider_receipt": receipt.raw,
            }
            self._audit(
                session,
                stored,
                "publication.cms_draft_reconciled",
                {
                    "provider": adapter.name,
                    "target": target,
                    "external_id": receipt.external_id,
                    "draft_id": str(draft_id),
                    "draft_version": draft_version,
                },
            )

        self._advance_package_ready(
            workflow_run_id,
            publication_id,
            draft_id=draft_id,
            draft_version=draft_version,
            adapter_name=adapter.name,
            target=target,
        )
        return self._publication(publication_id)

    def publish(
        self,
        publication_id: UUID,
        *,
        adapter: CMSAdapter,
        scheduled_at: datetime | None = None,
    ) -> Publication:
        with self.session_factory.begin() as session:
            publication = session.get(Publication, publication_id)
            if publication is None:
                raise PublicationPolicyError("Publication does not exist.")
            draft = session.get(Draft, publication.draft_id)
            run = session.get(WorkflowRun, publication.workflow_run_id)
            if draft is None or run is None:
                raise PublicationPolicyError(
                    "Publication references missing workflow data."
                )
            if publication.provider != adapter.name:
                raise PublicationPolicyError(
                    "Adapter does not match publication provider."
                )

            status = PublicationStatus(publication.status)
            workflow_run_id = publication.workflow_run_id
            if status is PublicationStatus.PUBLISHED:
                already_published = True
                document = None
                external_id = publication.external_id
                target = publication.target
                owner_key = publication.owner_key
                publish_key = f"{publication.idempotency_key}:publish"
            elif status is PublicationStatus.SCHEDULED:
                return self._detached(session, publication)
            else:
                already_published = False
                if WorkflowStatus(run.status) is not WorkflowStatus.PUBLISH_APPROVED:
                    raise PublicationPolicyError(
                        "Final publication requires workflow status PUBLISH_APPROVED."
                    )
                if not publication.external_id:
                    raise PublicationPolicyError(
                        "CMS draft must exist before final publication."
                    )
                self._assert_gate_c(session, publication)
                document = self._build_document(session, draft)
                external_id = publication.external_id
                target = publication.target
                owner_key = publication.owner_key
                publish_key = f"{publication.idempotency_key}:publish"

        if already_published:
            self._advance_publication_completed(
                workflow_run_id,
                publication_id,
                adapter_name=adapter.name,
            )
            return self._publication(publication_id)

        assert document is not None
        assert external_id is not None
        try:
            receipt = adapter.publish(
                document,
                external_id,
                target=target,
                owner_key=owner_key,
                idempotency_key=publish_key,
                scheduled_at=scheduled_at,
            )
        except CMSRetryableError as exc:
            self._mark_failure(
                publication_id,
                retryable=True,
                message=str(exc),
            )
            raise
        except CMSTerminalError as exc:
            self._mark_failure(
                publication_id,
                retryable=False,
                message=str(exc),
            )
            raise

        try:
            remote_status = PublicationStatus(receipt.status)
        except ValueError as exc:
            self._mark_failure(
                publication_id,
                retryable=False,
                message=f"Unsupported CMS publication status: {receipt.status}",
            )
            raise CMSTerminalError(
                f"Unsupported CMS publication status: {receipt.status}"
            ) from exc

        if remote_status not in {
            PublicationStatus.PUBLISHED,
            PublicationStatus.SCHEDULED,
        }:
            self._mark_failure(
                publication_id,
                retryable=False,
                message=(
                    "CMS publish receipt must be PUBLISHED or SCHEDULED, got "
                    f"{remote_status.value}."
                ),
            )
            raise CMSTerminalError(
                "CMS publish receipt did not represent a final publish action."
            )

        with self.session_factory.begin() as session:
            stored = session.get(Publication, publication_id)
            if stored is None:
                raise PublicationPolicyError(
                    "Publication disappeared while persisting the CMS receipt."
                )
            stored.status = remote_status.value
            stored.external_id = receipt.external_id
            stored.external_url = receipt.external_url
            stored.scheduled_at = receipt.scheduled_at or scheduled_at
            stored.published_at = (
                utcnow()
                if remote_status is PublicationStatus.PUBLISHED
                else None
            )
            stored.receipt = {
                "phase": remote_status.value.lower(),
                "adapter": adapter.name,
                "provider_receipt": receipt.raw,
            }
            self._audit(
                session,
                stored,
                (
                    "publication.completed"
                    if remote_status is PublicationStatus.PUBLISHED
                    else "publication.scheduled"
                ),
                {
                    "provider": adapter.name,
                    "target": stored.target,
                    "external_id": receipt.external_id,
                    "scheduled_at": (
                        stored.scheduled_at.isoformat()
                        if stored.scheduled_at
                        else None
                    ),
                },
            )

        if remote_status is PublicationStatus.PUBLISHED:
            self._advance_publication_completed(
                workflow_run_id,
                publication_id,
                adapter_name=adapter.name,
            )

        return self._publication(publication_id)

    @staticmethod
    def _assert_gate_c(
        session: Session,
        publication: Publication,
    ) -> None:
        approved = session.scalar(
            select(GateDecision.id).where(
                GateDecision.workflow_run_id == publication.workflow_run_id,
                GateDecision.gate == GateKind.PUBLISH.value,
                GateDecision.outcome == GateOutcome.APPROVED.value,
                GateDecision.artifact_type == "publication",
                GateDecision.artifact_id == publication.id,
                GateDecision.artifact_version == 1,
            )
        )
        if approved is None:
            raise PublicationPolicyError(
                "Gate C approval for the exact publication intent is required."
            )

    @staticmethod
    def _build_document(
        session: Session,
        draft: Draft,
    ) -> CMSDocument:
        manifest = session.scalar(
            select(AssetManifest)
            .where(AssetManifest.draft_id == draft.id)
            .order_by(AssetManifest.version.desc())
            .limit(1)
        )
        assets: tuple[CMSAsset, ...] = ()
        if manifest is not None:
            rows = tuple(
                session.scalars(
                    select(Asset)
                    .where(Asset.manifest_id == manifest.id)
                    .order_by(Asset.slot)
                )
            )
            assets = tuple(
                CMSAsset(
                    slot=item.slot,
                    kind=item.kind,
                    uri=item.uri,
                    alt_text=item.alt_text,
                    caption=item.caption,
                    filename=item.filename,
                    rights_status=item.rights_status,
                )
                for item in rows
            )

        return CMSDocument(
            title=draft.title,
            deck=draft.deck,
            body=draft.body,
            locale=draft.locale,
            metadata={
                "draft_id": str(draft.id),
                "draft_version": draft.version,
                "workflow_run_id": str(draft.workflow_run_id),
                "content_format": draft.content_format,
                "seo": draft.seo_metadata,
                "citations": draft.citations,
                "sections": draft.sections,
                "vertical_pack": {
                    "key": draft.vertical_pack_key,
                    "version": draft.vertical_pack_version,
                },
            },
            assets=assets,
        )

    def _advance_package_ready(
        self,
        workflow_run_id: UUID,
        publication_id: UUID,
        *,
        draft_id: UUID,
        draft_version: int,
        adapter_name: str,
        target: str,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise PublicationPolicyError("Workflow run does not exist.")
            status = WorkflowStatus(run.status)

        if status is WorkflowStatus.EDITORIAL_APPROVED:
            self.workflow_engine.apply(
                workflow_run_id,
                WorkflowCommand(
                    action_key=(
                        f"package-ready:{publication_id}:draft-v{draft_version}"
                    ),
                    action_type=WorkflowActionType.PACKAGE_READY,
                    actor_kind=AuditActorKind.SYSTEM,
                    actor_id=f"cms:{adapter_name}",
                    payload={
                        "publication_id": str(publication_id),
                        "draft_id": str(draft_id),
                        "draft_version": draft_version,
                        "provider": adapter_name,
                        "target": target,
                    },
                ),
            )
            return

        if status in {
            WorkflowStatus.READY_TO_PUBLISH,
            WorkflowStatus.PUBLISH_APPROVED,
            WorkflowStatus.PUBLISHED,
            WorkflowStatus.DISTRIBUTED,
            WorkflowStatus.MEASURED,
        }:
            return

        raise PublicationPolicyError(
            f"CMS package reconciliation is not legal from {status.value}."
        )

    def _advance_publication_completed(
        self,
        workflow_run_id: UUID,
        publication_id: UUID,
        *,
        adapter_name: str,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise PublicationPolicyError("Workflow run does not exist.")
            status = WorkflowStatus(run.status)

        if status is WorkflowStatus.PUBLISH_APPROVED:
            self.workflow_engine.apply(
                workflow_run_id,
                WorkflowCommand(
                    action_key=f"publication-completed:{publication_id}",
                    action_type=WorkflowActionType.PUBLICATION_COMPLETED,
                    actor_kind=AuditActorKind.SYSTEM,
                    actor_id=f"cms:{adapter_name}",
                    payload={"publication_id": str(publication_id)},
                ),
            )
            return

        if status in {
            WorkflowStatus.PUBLISHED,
            WorkflowStatus.DISTRIBUTED,
            WorkflowStatus.MEASURED,
        }:
            return

        raise PublicationPolicyError(
            f"Published CMS receipt cannot reconcile from {status.value}."
        )

    def _mark_failure(
        self,
        publication_id: UUID,
        *,
        retryable: bool,
        message: str,
    ) -> None:
        with self.session_factory.begin() as session:
            publication = session.get(Publication, publication_id)
            if publication is None:
                return
            publication.status = (
                PublicationStatus.FAILED_RETRYABLE.value
                if retryable
                else PublicationStatus.FAILED_TERMINAL.value
            )
            publication.receipt = {
                **publication.receipt,
                "last_error": message,
                "retryable": retryable,
            }
            self._audit(
                session,
                publication,
                "publication.failed",
                {"retryable": retryable, "message": message},
            )

    def _publication(self, publication_id: UUID) -> Publication:
        with self.session_factory() as session:
            publication = session.get(Publication, publication_id)
            if publication is None:
                raise PublicationPolicyError("Publication does not exist.")
            return self._detached(session, publication)

    @staticmethod
    def _detached(
        session: Session,
        publication: Publication,
    ) -> Publication:
        session.expunge(publication)
        return publication

    @staticmethod
    def _audit(
        session: Session,
        publication: Publication,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        session.add(
            AuditEvent(
                workflow_run_id=publication.workflow_run_id,
                actor_kind=AuditActorKind.SYSTEM.value,
                actor_id=f"cms:{publication.provider}",
                event_type=event_type,
                entity_type="publication",
                entity_id=publication.id,
                occurred_at=utcnow(),
                payload=payload,
            )
        )

    @staticmethod
    def _idempotency_key(
        provider: str,
        target: str,
        draft_id: UUID,
        draft_version: int,
    ) -> str:
        raw = f"{provider}|{target}|{draft_id}|{draft_version}".encode()
        return f"publication:{sha256(raw).hexdigest()}"
