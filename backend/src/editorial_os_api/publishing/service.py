from __future__ import annotations

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
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.workflow_engine = PostgresWorkflowEngine(session_factory)

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
            if WorkflowStatus(run.status) not in {
                WorkflowStatus.EDITORIAL_APPROVED,
                WorkflowStatus.READY_TO_PUBLISH,
                WorkflowStatus.PUBLISH_APPROVED,
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
            owner_key = f"editorial-os:{run.id}:{draft.locale}"
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

            if publication.external_id and publication.status == PublicationStatus.DRAFT.value:
                return publication
            if publication.status == PublicationStatus.PUBLISHED.value:
                return publication

            document = self._build_document(session, draft)

        try:
            receipt = adapter.upsert_draft(
                document,
                target=target,
                owner_key=owner_key,
                idempotency_key=idempotency_key,
                existing_external_id=publication.external_id,
            )
        except CMSRetryableError as exc:
            self._mark_failure(publication.id, retryable=True, message=str(exc))
            raise
        except CMSTerminalError as exc:
            self._mark_failure(publication.id, retryable=False, message=str(exc))
            raise

        with self.session_factory.begin() as session:
            stored = session.get(Publication, publication.id)
            assert stored is not None
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
                },
            )
            session.flush()
            session.refresh(stored)
            return stored

    def publish(
        self,
        publication_id: UUID,
        *,
        adapter: CMSAdapter,
    ) -> Publication:
        with self.session_factory.begin() as session:
            publication = session.get(Publication, publication_id)
            if publication is None:
                raise PublicationPolicyError("Publication does not exist.")
            draft = session.get(Draft, publication.draft_id)
            run = session.get(WorkflowRun, publication.workflow_run_id)
            if draft is None or run is None:
                raise PublicationPolicyError("Publication references missing workflow data.")

            if publication.provider != adapter.name:
                raise PublicationPolicyError("Adapter does not match publication provider.")

            if publication.status == PublicationStatus.PUBLISHED.value:
                should_advance = run.status == WorkflowStatus.PUBLISH_APPROVED.value
                stored_id = publication.id
            else:
                should_advance = False
                stored_id = publication.id
                if run.status != WorkflowStatus.PUBLISH_APPROVED.value:
                    raise PublicationPolicyError(
                        "Final publication requires workflow status PUBLISH_APPROVED."
                    )
                if not publication.external_id:
                    raise PublicationPolicyError(
                        "CMS draft must exist before final publication."
                    )
                self._assert_gate_c(session, draft)
                external_id = publication.external_id
                target = publication.target
                owner_key = publication.owner_key
                publish_key = f"{publication.idempotency_key}:publish"

        if publication.status != PublicationStatus.PUBLISHED.value:
            try:
                receipt = adapter.publish(
                    external_id,
                    target=target,
                    owner_key=owner_key,
                    idempotency_key=publish_key,
                )
            except CMSRetryableError as exc:
                self._mark_failure(stored_id, retryable=True, message=str(exc))
                raise
            except CMSTerminalError as exc:
                self._mark_failure(stored_id, retryable=False, message=str(exc))
                raise

            with self.session_factory.begin() as session:
                stored = session.get(Publication, stored_id)
                assert stored is not None
                stored.status = PublicationStatus.PUBLISHED.value
                stored.external_id = receipt.external_id
                stored.external_url = receipt.external_url
                stored.published_at = utcnow()
                stored.receipt = {
                    "phase": "published",
                    "adapter": adapter.name,
                    "provider_receipt": receipt.raw,
                }
                self._audit(
                    session,
                    stored,
                    "publication.completed",
                    {
                        "provider": adapter.name,
                        "target": stored.target,
                        "external_id": receipt.external_id,
                    },
                )

            should_advance = True

        if should_advance:
            self.workflow_engine.apply(
                publication.workflow_run_id,
                WorkflowCommand(
                    action_key=f"publication-completed:{stored_id}",
                    action_type=WorkflowActionType.PUBLICATION_COMPLETED,
                    actor_kind=AuditActorKind.SYSTEM,
                    actor_id=f"cms:{adapter.name}",
                    payload={"publication_id": str(stored_id)},
                ),
            )

        with self.session_factory() as session:
            final = session.get(Publication, stored_id)
            assert final is not None
            session.expunge(final)
            return final

    @staticmethod
    def _assert_gate_c(session: Session, draft: Draft) -> None:
        approved = session.scalar(
            select(GateDecision.id).where(
                GateDecision.workflow_run_id == draft.workflow_run_id,
                GateDecision.gate == GateKind.PUBLISH.value,
                GateDecision.outcome == GateOutcome.APPROVED.value,
                GateDecision.artifact_id == draft.id,
                GateDecision.artifact_version == draft.version,
            )
        )
        if approved is None:
            raise PublicationPolicyError(
                "Gate C approval for the exact draft version is required."
            )

    @staticmethod
    def _build_document(session: Session, draft: Draft) -> CMSDocument:
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
                "vertical_pack": {
                    "key": draft.vertical_pack_key,
                    "version": draft.vertical_pack_version,
                },
            },
            assets=assets,
        )

    def _mark_failure(self, publication_id: UUID, *, retryable: bool, message: str) -> None:
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
