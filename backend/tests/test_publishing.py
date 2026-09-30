from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from editorial_os_api.domain.enums import (
    GateKind,
    GateOutcome,
    PublicationStatus,
    WorkflowStatus,
)
from editorial_os_api.persistence.models import (
    Asset,
    AssetManifest,
    Draft,
    EditorialBrief,
    GateDecision,
    Publication,
    WorkflowRun,
)
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.publishing import (
    CMSDocument,
    CMSDraftReceipt,
    CMSPublishReceipt,
    CMSRetryableError,
    PublicationPolicyError,
    PublishingService,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _create_ready_draft(*, with_asset: bool = False) -> UUID:
    _upgrade_schema()
    with get_session_factory().begin() as session:
        run = WorkflowRun(
            vertical_key="fixture",
            vertical_version="1",
            status=WorkflowStatus.READY_TO_PUBLISH.value,
            risk_class="R0",
            confidence_class="C4",
            policy_version="1",
            idempotency_key=f"publish-run-{uuid4().hex}",
            context={},
        )
        session.add(run)
        session.flush()

        brief = EditorialBrief(
            workflow_run_id=run.id,
            version=1,
            angle="Publish a verified fixture.",
            locale="fr",
            instructions={},
        )
        session.add(brief)
        session.flush()

        draft = Draft(
            workflow_run_id=run.id,
            editorial_brief_id=brief.id,
            version=1,
            locale="fr",
            content_format="article",
            vertical_pack_key="fixture",
            vertical_pack_version="1",
            input_fingerprint=f"publish-draft-{uuid4().hex}",
            title="Article de test",
            deck="Un chapeau de test.",
            body="Contenu vérifié.",
            sections=[],
            seo_metadata={"description": "Résumé SEO"},
            citations=[],
            internal_link_suggestions=[],
            unsupported_factual_claims=[],
            vertical_pack_snapshot={},
            metadata_payload={},
        )
        session.add(draft)
        session.flush()

        if with_asset:
            manifest = AssetManifest(
                workflow_run_id=run.id,
                draft_id=draft.id,
                version=1,
                input_fingerprint=f"manifest-{uuid4().hex}",
                status="READY",
                text_only=False,
                rights_status="CLEAR",
                provider_name="fixture-images",
                provider_request_count=1,
                visual_brief={},
                asset_ids=[],
                approval_snapshot={},
                vertical_pack_snapshot={},
            )
            session.add(manifest)
            session.flush()
            asset = Asset(
                workflow_run_id=run.id,
                manifest_id=manifest.id,
                version=1,
                slot="hero",
                kind="IMAGE",
                origin="GENERATED",
                provider="fixture-images",
                uri="https://assets.example.test/hero.webp",
                filename="hero.webp",
                rights_status="CLEAR",
                alt_text="Visuel de test",
                caption="Légende de test",
                generation_metadata={"model": "fixture"},
                variants=[],
                provenance={"fixture": True},
                owner_key=f"asset-{uuid4().hex}",
            )
            session.add(asset)
            session.flush()
            manifest.asset_ids = [str(asset.id)]

        return draft.id


def _approve_gate_c(publication_id: UUID) -> UUID:
    with get_session_factory().begin() as session:
        publication = session.get(Publication, publication_id)
        assert publication is not None
        run = session.get(WorkflowRun, publication.workflow_run_id)
        assert run is not None
        run.status = WorkflowStatus.PUBLISH_APPROVED.value
        session.add(
            GateDecision(
                workflow_run_id=run.id,
                gate=GateKind.PUBLISH.value,
                outcome=GateOutcome.APPROVED.value,
                artifact_type="publication",
                artifact_id=publication.id,
                artifact_version=1,
                actor_id="fixture-operator",
                reason=None,
                decided_at=datetime.now(UTC),
                policy_version="1",
                details={"target": publication.target},
            )
        )
        return run.id


class FixtureCMS:
    name = "fixture-cms"

    def __init__(self, *, fail_draft_once: bool = False) -> None:
        self.fail_draft_once = fail_draft_once
        self.draft_calls = 0
        self.publish_calls = 0
        self.documents: list[CMSDocument] = []

    def upsert_draft(
        self,
        document: CMSDocument,
        *,
        target: str,
        owner_key: str,
        idempotency_key: str,
        existing_external_id: str | None,
    ) -> CMSDraftReceipt:
        del target, owner_key, idempotency_key, existing_external_id
        self.draft_calls += 1
        if self.fail_draft_once and self.draft_calls == 1:
            raise CMSRetryableError("fixture outage")
        self.documents.append(document)
        return CMSDraftReceipt(
            external_id="payload-42",
            external_url="https://cms.example.test/preview/42",
            raw={"id": "payload-42", "_status": "draft"},
        )

    def publish(
        self,
        document: CMSDocument,
        external_id: str,
        *,
        target: str,
        owner_key: str,
        idempotency_key: str,
        scheduled_at: datetime | None = None,
    ) -> CMSPublishReceipt:
        del document, target, owner_key, idempotency_key, scheduled_at
        self.publish_calls += 1
        return CMSPublishReceipt(
            external_id=external_id,
            external_url="https://example.test/articles/42",
            raw={"id": external_id, "_status": "published"},
        )


def test_retrying_same_cms_draft_creates_no_duplicate_and_maps_locale_assets() -> None:
    draft_id = _create_ready_draft(with_asset=True)
    adapter = FixtureCMS()
    service = PublishingService(get_session_factory())

    first = service.ensure_cms_draft(draft_id, adapter=adapter, target="staging")
    second = service.ensure_cms_draft(draft_id, adapter=adapter, target="staging")

    assert first.id == second.id
    assert first.external_id == "payload-42"
    assert adapter.draft_calls == 1
    assert adapter.documents[0].locale == "fr"
    assert adapter.documents[0].metadata["draft_version"] == 1
    assert len(adapter.documents[0].assets) == 1
    assert adapter.documents[0].assets[0].slot == "hero"

    with get_session_factory()() as session:
        rows = list(
            session.scalars(
                select(Publication).where(
                    Publication.workflow_run_id == first.workflow_run_id
                )
            )
        )
        assert len(rows) == 1


def test_payload_outage_leaves_retryable_publication_and_retry_recovers() -> None:
    draft_id = _create_ready_draft()
    adapter = FixtureCMS(fail_draft_once=True)
    service = PublishingService(get_session_factory())

    with pytest.raises(CMSRetryableError):
        service.ensure_cms_draft(draft_id, adapter=adapter, target="staging")

    with get_session_factory()() as session:
        publication = session.scalar(
            select(Publication).where(Publication.draft_id == draft_id)
        )
        assert publication is not None
        assert publication.status == PublicationStatus.FAILED_RETRYABLE.value

    recovered = service.ensure_cms_draft(draft_id, adapter=adapter, target="staging")
    assert recovered.status == PublicationStatus.DRAFT.value
    assert recovered.external_id == "payload-42"
    assert adapter.draft_calls == 2


def test_final_publish_is_blocked_without_gate_c() -> None:
    draft_id = _create_ready_draft()
    adapter = FixtureCMS()
    service = PublishingService(get_session_factory())
    publication = service.ensure_cms_draft(draft_id, adapter=adapter, target="staging")

    with pytest.raises(PublicationPolicyError):
        service.publish(publication.id, adapter=adapter)

    assert adapter.publish_calls == 0


def test_gate_c_exact_draft_version_is_required() -> None:
    draft_id = _create_ready_draft()
    adapter = FixtureCMS()
    service = PublishingService(get_session_factory())
    publication = service.ensure_cms_draft(draft_id, adapter=adapter, target="staging")

    with get_session_factory().begin() as session:
        draft = session.get(Draft, draft_id)
        assert draft is not None
        run = session.get(WorkflowRun, draft.workflow_run_id)
        assert run is not None
        run.status = WorkflowStatus.PUBLISH_APPROVED.value
        session.add(
            GateDecision(
                workflow_run_id=run.id,
                gate=GateKind.PUBLISH.value,
                outcome=GateOutcome.APPROVED.value,
                artifact_type="draft",
                artifact_id=draft.id,
                artifact_version=draft.version + 1,
                actor_id="fixture-operator",
                reason=None,
                decided_at=datetime.now(UTC),
                policy_version="1",
                details={},
            )
        )

    with pytest.raises(PublicationPolicyError):
        service.publish(publication.id, adapter=adapter)

    assert adapter.publish_calls == 0


def test_draft_approve_publish_lifecycle_is_idempotent() -> None:
    draft_id = _create_ready_draft()
    adapter = FixtureCMS()
    service = PublishingService(get_session_factory())
    publication = service.ensure_cms_draft(draft_id, adapter=adapter, target="staging")
    run_id = _approve_gate_c(publication.id)

    published = service.publish(publication.id, adapter=adapter)
    replay = service.publish(publication.id, adapter=adapter)

    assert published.status == PublicationStatus.PUBLISHED.value
    assert replay.id == published.id
    assert adapter.publish_calls == 1

    with get_session_factory()() as session:
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        assert run.status == WorkflowStatus.PUBLISHED.value
