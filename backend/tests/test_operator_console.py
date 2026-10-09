from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import NullPool

from editorial_os_api.config import Settings
from editorial_os_api.db import get_engine
from editorial_os_api.main import app, create_app
from editorial_os_api.persistence.models import (
    GateDecision,
    ModelUsageRecord,
    TopicCandidate,
    WorkflowRun,
)
from editorial_os_api.persistence.session import get_session_factory

BACKEND_DIR = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _run(*, status: str, resume_status: str | None = None) -> WorkflowRun:
    _upgrade_schema()
    with get_session_factory().begin() as session:
        run = WorkflowRun(
            vertical_key="operator-fixture",
            vertical_version="1",
            status=status,
            risk_class="R1",
            confidence_class="C3",
            policy_version="1",
            idempotency_key=f"operator-{uuid4().hex}",
            context={"provider_api_token": "must-never-reach-browser"},
            resume_status=resume_status,
        )
        session.add(run)
        session.flush()
        session.expunge(run)
        return run


def _candidate_run() -> tuple[WorkflowRun, TopicCandidate]:
    run = _run(status="CANDIDATE")
    with get_session_factory().begin() as session:
        topic = TopicCandidate(
            workflow_run_id=run.id,
            version=1,
            cluster_key=f"topic-{uuid4().hex}",
            title="Operator fixture topic",
            proposed_angle="Inspect the evidence before approval.",
            proposed_format="article",
            urgency="NORMAL",
            decision="PROPOSE",
            novelty_score=80,
            relevance_score=90,
            source_diversity_score=70,
            composite_score=82,
            risk_class="R1",
            confidence_class="C3",
            reason_codes=["fixture"],
            source_item_ids=[],
            reason_details={},
        )
        session.add(topic)
        session.flush()
        session.expunge(topic)
        return run, topic


def test_operator_queue_filters_and_never_exposes_run_context() -> None:
    run, _ = _candidate_run()
    with get_session_factory().begin() as session:
        session.add(
            ModelUsageRecord(
                workflow_run_id=run.id,
                agent_id="fixture-agent",
                task="fixture-task",
                call_key=f"call-{uuid4().hex}",
                route_name="fixture",
                provider_model="fixture/model",
                status="SUCCEEDED",
                reserved_cost_usd=Decimal("0.010000"),
                actual_cost_usd=Decimal("0.008000"),
                cost_is_estimated=False,
                input_tokens=100,
                output_tokens=40,
                latency_ms=250,
            )
        )

    response = client.get(
        "/api/operator/runs",
        params={
            "vertical": "operator-fixture",
            "status": "CANDIDATE",
            "topic_decision": "PROPOSE",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert any(item["id"] == str(run.id) for item in payload)

    detail = client.get(f"/api/operator/runs/{run.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["run"]["pending_gate"] == "A"
    assert body["usage"]["calls"] == 1
    assert body["usage"]["input_tokens"] == 100
    assert "context" not in body["run"]
    assert "must-never-reach-browser" not in detail.text


def test_gate_action_resolves_canonical_artifact_server_side_and_audits_actor() -> None:
    run, topic = _candidate_run()

    bypass = client.post(
        f"/api/operator/runs/{run.id}/gate",
        json={
            "outcome": "APPROVED",
            "actor_id": "operator@example.test",
            "artifact_id": str(uuid4()),
        },
    )
    assert bypass.status_code == 422

    response = client.post(
        f"/api/operator/runs/{run.id}/gate",
        json={
            "outcome": "APPROVED",
            "actor_id": "operator@example.test",
            "reason": "Evidence reviewed.",
            "details": {"device": "tablet"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["status"] == "TOPIC_APPROVED"
    assert payload["run"]["state_version"] == 1

    with get_session_factory()() as session:
        decision = session.scalar(
            select(GateDecision)
            .where(GateDecision.workflow_run_id == run.id)
            .order_by(GateDecision.decided_at.desc())
            .limit(1)
        )
        assert decision is not None
        assert decision.gate == "A"
        assert decision.artifact_type == "topic_candidate"
        assert decision.artifact_id == topic.id
        assert decision.artifact_version == topic.version
        assert decision.actor_id == "operator@example.test"
        assert decision.reason == "Evidence reviewed."
        assert decision.details["surface"] == "operator-console"


def test_operator_cannot_decide_a_gate_from_a_non_gate_state() -> None:
    run = _run(status="VERIFIED")

    response = client.post(
        f"/api/operator/runs/{run.id}/gate",
        json={
            "outcome": "APPROVED",
            "actor_id": "operator@example.test",
        },
    )

    assert response.status_code == 409
    assert "no gate awaiting" in response.json()["detail"].lower()


def test_retryable_run_can_be_recovered_from_console() -> None:
    run = _run(status="FAILED_RETRYABLE", resume_status="VERIFIED")

    response = client.post(
        f"/api/operator/runs/{run.id}/recover",
        json={
            "actor_id": "operator@example.test",
            "reason": "Provider is healthy again.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["status"] == "VERIFIED"
    assert payload["recovery_action"] is None


def test_recovery_is_rejected_when_workflow_state_does_not_allow_it() -> None:
    run = _run(status="PUBLISHED")

    response = client.post(
        f"/api/operator/runs/{run.id}/recover",
        json={"actor_id": "operator@example.test"},
    )

    assert response.status_code == 409
    assert "not legal" in response.json()["detail"].lower()


def test_staging_operator_api_requires_bearer_token() -> None:
    protected = TestClient(
        create_app(
            Settings(
                environment="staging",
                operator_api_token="operator-secret",
                langfuse_enabled=False,
                posthog_enabled=False,
                payload_enabled=False,
                postiz_enabled=False,
                n8n_enabled=False,
                remotion_enabled=False,
            )
        )
    )

    missing = protected.get("/api/operator/runs")
    assert missing.status_code == 401

    invalid = protected.get(
        "/api/operator/runs",
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert invalid.status_code == 401


def test_staging_operator_api_fails_closed_without_configured_secret() -> None:
    protected = TestClient(
        create_app(
            Settings(
                environment="staging",
                operator_api_token=None,
                langfuse_enabled=False,
                posthog_enabled=False,
                payload_enabled=False,
                postiz_enabled=False,
                n8n_enabled=False,
                remotion_enabled=False,
            )
        )
    )

    response = protected.get(
        "/api/operator/runs",
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 503


def test_hyperdrive_engine_does_not_pool_worker_request_sockets() -> None:
    engine = get_engine(
        Settings(
            database_url="postgresql+pg8000://worker:secret@127.0.0.1:5432/editorial",
            database_echo=False,
        )
    )
    assert isinstance(engine.pool, NullPool)
