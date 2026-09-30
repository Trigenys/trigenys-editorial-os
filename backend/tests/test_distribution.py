from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from editorial_os_api.config import Settings
from editorial_os_api.distribution import (
    ChannelVariant,
    DistributionReceipt,
    DistributionReconciliationRequired,
    DistributionRetryableError,
    DistributionService,
    PerformanceService,
    PostHogPerformanceEventParser,
    PostizAdapter,
)
from editorial_os_api.domain.enums import DistributionStatus, WorkflowStatus
from editorial_os_api.persistence.models import (
    AuditEvent,
    DistributionJob,
    Draft,
    EditorialBrief,
    PerformanceSnapshot,
    Publication,
    TopicCandidate,
    WorkflowRun,
)
from editorial_os_api.persistence.session import get_session_factory

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _create_published_fixture() -> tuple[UUID, UUID, UUID]:
    _upgrade_schema()
    now = datetime.now(UTC)
    with get_session_factory().begin() as session:
        run = WorkflowRun(
            vertical_key="fixture",
            vertical_version="1",
            status=WorkflowStatus.PUBLISHED.value,
            risk_class="R0",
            confidence_class="C4",
            policy_version="1",
            idempotency_key=f"distribution-run-{uuid4().hex}",
            context={},
        )
        session.add(run)
        session.flush()

        topic = TopicCandidate(
            workflow_run_id=run.id,
            version=1,
            cluster_key=f"distribution-topic-{uuid4().hex}",
            title="Fixture distribution topic",
            proposed_angle="Explain the verified fixture.",
            decision="PROPOSE",
            risk_class="R0",
            confidence_class="C4",
            reason_codes=["fixture"],
            source_item_ids=[],
        )
        brief = EditorialBrief(
            workflow_run_id=run.id,
            version=1,
            angle="Explain the verified fixture.",
            locale="en",
            instructions={},
        )
        session.add_all([topic, brief])
        session.flush()

        draft = Draft(
            workflow_run_id=run.id,
            editorial_brief_id=brief.id,
            version=1,
            locale="en",
            content_format="article",
            vertical_pack_key="fixture",
            vertical_pack_version="1",
            input_fingerprint=f"distribution-draft-{uuid4().hex}",
            title="A useful canonical article",
            deck="The short explanation readers need before opening the full story.",
            body="Verified canonical body.",
            sections=[],
            seo_metadata={},
            citations=[],
            internal_link_suggestions=[],
            unsupported_factual_claims=[],
            vertical_pack_snapshot={},
            metadata_payload={},
        )
        session.add(draft)
        session.flush()

        publication = Publication(
            workflow_run_id=run.id,
            draft_id=draft.id,
            provider="payload",
            target="trigenys-insight",
            status="PUBLISHED",
            owner_key=f"publication-{uuid4().hex}",
            idempotency_key=f"publication-{uuid4().hex}",
            external_id=f"article-{uuid4().hex}",
            external_url="https://trigenys.example/articles/useful-canonical-article",
            scheduled_at=None,
            published_at=now,
            receipt={"fixture": True},
        )
        session.add(publication)
        session.flush()
        return publication.id, run.id, topic.id


class FixtureSocialAdapter:
    name = "fixture-social"

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.calls = 0
        self.idempotency_keys: list[str] = []

    def deliver(
        self,
        variant: ChannelVariant,
        *,
        owner_key: str,
        idempotency_key: str,
    ) -> DistributionReceipt:
        del owner_key
        self.calls += 1
        self.idempotency_keys.append(idempotency_key)
        if self.mode == "retry-once" and self.calls == 1:
            raise DistributionRetryableError("provider rejected before delivery")
        if self.mode == "ambiguous":
            raise DistributionReconciliationRequired("delivery outcome unknown")
        return DistributionReceipt(
            external_id="social-42",
            status=DistributionStatus.SCHEDULED.value,
            external_url="https://social.example/posts/42",
            scheduled_at=variant.scheduled_at,
            raw={"ok": True},
        )


def test_preview_generates_channel_copy_without_posting() -> None:
    publication_id, run_id, _ = _create_published_fixture()
    service = DistributionService(get_session_factory())

    job = service.preview(
        publication_id,
        provider="fixture-social",
        channel="x",
        integration_id="x-account-1",
    )

    assert job.status == DistributionStatus.PREVIEW.value
    assert "A useful canonical article" in str(job.payload["content"])
    assert "https://trigenys.example/articles/useful-canonical-article" in str(
        job.payload["content"]
    )
    assert len(str(job.payload["content"])) <= 280

    with get_session_factory()() as session:
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        assert run.status == WorkflowStatus.PUBLISHED.value


def test_successful_distribution_is_audited_and_retry_does_not_double_post() -> None:
    publication_id, run_id, _ = _create_published_fixture()
    service = DistributionService(get_session_factory())
    adapter = FixtureSocialAdapter()
    scheduled_at = datetime.now(UTC) + timedelta(hours=2)

    preview = service.preview(
        publication_id,
        provider=adapter.name,
        channel="linkedin",
        integration_id="linkedin-page-1",
        scheduled_at=scheduled_at,
    )
    first = service.dispatch(preview.id, adapter=adapter)
    second = service.dispatch(preview.id, adapter=adapter)

    assert first.status == DistributionStatus.SCHEDULED.value
    assert second.id == first.id
    assert adapter.calls == 1
    assert len(adapter.idempotency_keys) == 1

    with get_session_factory()() as session:
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        assert run.status == WorkflowStatus.DISTRIBUTED.value
        audit_count = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.workflow_run_id == run_id,
                AuditEvent.event_type == "distribution.scheduled",
            )
        )
        assert audit_count == 1


def test_retryable_channel_failure_does_not_roll_back_article() -> None:
    publication_id, run_id, _ = _create_published_fixture()
    service = DistributionService(get_session_factory())
    adapter = FixtureSocialAdapter(mode="retry-once")

    preview = service.preview(
        publication_id,
        provider=adapter.name,
        channel="x",
        integration_id="x-account-1",
    )

    with pytest.raises(DistributionRetryableError):
        service.dispatch(preview.id, adapter=adapter)

    with get_session_factory()() as session:
        job = session.get(DistributionJob, preview.id)
        publication = session.get(Publication, publication_id)
        run = session.get(WorkflowRun, run_id)
        assert job is not None
        assert publication is not None
        assert run is not None
        assert job.status == DistributionStatus.FAILED_RETRYABLE.value
        assert publication.status == "PUBLISHED"
        assert run.status == WorkflowStatus.PUBLISHED.value

    recovered = service.dispatch(preview.id, adapter=adapter)
    assert recovered.status == DistributionStatus.SCHEDULED.value
    assert adapter.calls == 2


def test_ambiguous_delivery_requires_reconciliation_before_retry() -> None:
    publication_id, _, _ = _create_published_fixture()
    service = DistributionService(get_session_factory())
    adapter = FixtureSocialAdapter(mode="ambiguous")
    preview = service.preview(
        publication_id,
        provider=adapter.name,
        channel="x",
        integration_id="x-account-1",
    )

    with pytest.raises(DistributionReconciliationRequired):
        service.dispatch(preview.id, adapter=adapter)
    with pytest.raises(DistributionReconciliationRequired):
        service.dispatch(preview.id, adapter=adapter)

    assert adapter.calls == 1
    with get_session_factory()() as session:
        job = session.get(DistributionJob, preview.id)
        assert job is not None
        assert job.status == DistributionStatus.DISPATCHING.value
        assert job.receipt["reconciliation_required"] is True


def test_posthog_performance_maps_to_article_topic_run_and_is_idempotent() -> None:
    publication_id, run_id, topic_id = _create_published_fixture()
    distribution = DistributionService(get_session_factory())
    adapter = FixtureSocialAdapter()
    preview = distribution.preview(
        publication_id,
        provider=adapter.name,
        channel="linkedin",
        integration_id="linkedin-page-1",
    )
    delivered = distribution.dispatch(preview.id, adapter=adapter)

    parser = PostHogPerformanceEventParser()
    event = parser.parse(
        {
            "uuid": "posthog-event-42",
            "timestamp": "2026-09-30T10:00:00Z",
            "properties": {
                "workflow_run_id": str(run_id),
                "publication_id": str(publication_id),
                "distribution_job_id": str(delivered.id),
                "metrics": {
                    "views": 420,
                    "clicks": 21,
                    "ctr": 0.05,
                },
            },
        }
    )
    service = PerformanceService(get_session_factory())
    first = service.ingest(event)
    second = service.ingest(event)

    assert first.id == second.id
    assert first.workflow_run_id == run_id
    assert first.topic_candidate_id == topic_id
    assert first.publication_id == publication_id
    assert first.distribution_job_id == delivered.id
    assert first.provider == "posthog"
    assert first.metrics["views"] == 420

    with get_session_factory()() as session:
        count = session.scalar(
            select(func.count())
            .select_from(PerformanceSnapshot)
            .where(PerformanceSnapshot.event_key == "posthog-event-42")
        )
        assert count == 1
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        assert run.status == WorkflowStatus.MEASURED.value


def test_postiz_adapter_uses_public_posts_contract_and_stable_headers() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["idempotency"] = request.headers["idempotency-key"]
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "postiz-42",
                "url": "https://social.example/postiz-42",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = PostizAdapter(
        api_key="postiz-test-key",
        client=client,
    )
    scheduled_at = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    receipt = adapter.deliver(
        ChannelVariant(
            channel="linkedin",
            integration_id="integration-42",
            content="A useful update",
            scheduled_at=scheduled_at,
        ),
        owner_key="owner-42",
        idempotency_key="distribution-42",
    )

    assert captured["url"] == "https://api.postiz.com/public/v1/posts"
    assert captured["authorization"] == "postiz-test-key"
    assert captured["idempotency"] == "distribution-42"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["type"] == "schedule"
    posts = payload["posts"]
    assert isinstance(posts, list)
    assert posts[0]["integration"]["id"] == "integration-42"
    assert receipt.status == DistributionStatus.SCHEDULED.value


def test_distribution_integrations_are_off_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.postiz_enabled is False
    assert settings.n8n_enabled is False
    assert settings.remotion_enabled is False
