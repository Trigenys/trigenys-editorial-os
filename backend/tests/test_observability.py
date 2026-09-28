import json
import logging
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from editorial_os_api.domain.enums import AuditActorKind, WorkflowActionType, WorkflowStatus
from editorial_os_api.main import create_app
from editorial_os_api.model_gateway import (
    BudgetLedger,
    BudgetPolicy,
    ModelGateway,
    ModelMessage,
    ModelPolicy,
    ModelRequest,
    ModelRole,
    ModelRoute,
    ModelTask,
)
from editorial_os_api.model_gateway.fake import DeterministicFakeModel
from editorial_os_api.observability import (
    EvaluationTelemetryEvent,
    ModelTelemetryEvent,
    ObservabilityHub,
    ProductTelemetryEvent,
    bind_correlation,
)
from editorial_os_api.observability.adapters import (
    LangfuseTelemetrySink,
    PostHogTelemetrySink,
)
from editorial_os_api.observability.logging import JsonFormatter
from editorial_os_api.observability.redaction import REDACTED, redact, redact_text
from editorial_os_api.orchestration.engine import PostgresWorkflowEngine
from editorial_os_api.orchestration.models import WorkflowCommand
from editorial_os_api.orchestration.observed import ObservedWorkflowEngine
from editorial_os_api.persistence.models import WorkflowRun
from editorial_os_api.persistence.session import get_session_factory

BACKEND_DIR = Path(__file__).resolve().parents[1]


class CollectingSink:
    def __init__(self) -> None:
        self.model_events: list[ModelTelemetryEvent] = []
        self.evaluation_events: list[EvaluationTelemetryEvent] = []
        self.product_events: list[ProductTelemetryEvent] = []
        self.shutdown_called = False

    def record_model_call(self, event: ModelTelemetryEvent) -> None:
        self.model_events.append(event)

    def record_evaluation(self, event: EvaluationTelemetryEvent) -> None:
        self.evaluation_events.append(event)

    def record_product_event(self, event: ProductTelemetryEvent) -> None:
        self.product_events.append(event)

    def shutdown(self) -> None:
        self.shutdown_called = True


class FailingSink:
    def record_model_call(self, event: ModelTelemetryEvent) -> None:
        del event
        raise RuntimeError("telemetry offline")

    def record_evaluation(self, event: EvaluationTelemetryEvent) -> None:
        del event
        raise RuntimeError("telemetry offline")

    def record_product_event(self, event: ProductTelemetryEvent) -> None:
        del event
        raise RuntimeError("telemetry offline")

    def shutdown(self) -> None:
        raise RuntimeError("telemetry offline")


class FakeObservation:
    def __init__(self) -> None:
        self.ended = False

    def end(self) -> None:
        self.ended = True


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.trace_seeds: list[str] = []
        self.observations: list[dict[str, object]] = []
        self.scores: list[dict[str, object]] = []
        self.shutdown_called = False

    def create_trace_id(self, *, seed: str) -> str:
        self.trace_seeds.append(seed)
        return "a" * 32

    def start_observation(self, **kwargs: object) -> FakeObservation:
        self.observations.append(dict(kwargs))
        return FakeObservation()

    def create_score(self, **kwargs: object) -> None:
        self.scores.append(dict(kwargs))

    def shutdown(self) -> None:
        self.shutdown_called = True


class FakePostHogClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.shutdown_called = False

    def capture(
        self,
        event: str,
        *,
        distinct_id: str,
        properties: dict[str, object],
    ) -> None:
        self.calls.append((event, distinct_id, properties))

    def shutdown(self) -> None:
        self.shutdown_called = True


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _create_run() -> UUID:
    _upgrade_schema()
    run = WorkflowRun(
        vertical_key="observability-fixture",
        vertical_version="1",
        status=WorkflowStatus.INGESTED.value,
        risk_class="R0",
        confidence_class="C0",
        policy_version="1",
        idempotency_key=f"obs-run-{uuid4().hex}",
        context={},
    )
    with get_session_factory().begin() as session:
        session.add(run)
        session.flush()
        run_id = run.id
    return run_id


def _model_event(run_id: UUID) -> ModelTelemetryEvent:
    return ModelTelemetryEvent(
        workflow_run_id=run_id,
        agent_id="editorial-intelligence",
        task="editorial_intelligence",
        call_key="call-1",
        route_name="primary",
        provider_model="provider/model",
        status="completed",
        input_tokens=12,
        output_tokens=8,
        cost_usd=Decimal("0.012"),
        latency_ms=42,
        model_input={"authorization": "Bearer raw-secret"},
        model_output="sk-super-secret-value",
    )


def test_redaction_masks_nested_and_text_credentials() -> None:
    safe = redact(
        {
            "password": "hunter2",
            "nested": {
                "api_key": "abc",
                "note": "Authorization: Bearer abc.def token=xyz",
            },
            "database": "postgresql://user:password@db.internal/app",
        }
    )

    assert isinstance(safe, dict)
    assert safe["password"] == REDACTED
    nested = safe["nested"]
    assert isinstance(nested, dict)
    assert nested["api_key"] == REDACTED
    assert "abc.def" not in str(nested["note"])
    assert "xyz" not in str(nested["note"])
    assert "password@db.internal" not in str(safe["database"])
    assert REDACTED in redact_text("secret=abc123")


def test_json_logs_include_run_correlation_and_redact_secrets() -> None:
    run_id = uuid4()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request token=raw-token",
        args=(),
        exc_info=None,
    )
    record.event_name = "test event"
    record.event_data = {"authorization": "Bearer secret-token"}

    with bind_correlation(
        request_id="req-123",
        workflow_run_id=run_id,
        agent_id="qa",
        call_key="call-123",
    ):
        payload = json.loads(JsonFormatter().format(record))

    assert payload["correlation_id"] == str(run_id)
    assert payload["request_id"] == "req-123"
    assert payload["workflow_run_id"] == str(run_id)
    assert payload["agent_id"] == "qa"
    assert "raw-token" not in payload["message"]
    assert "secret-token" not in json.dumps(payload)


def test_hub_is_best_effort_and_continues_after_sink_failure() -> None:
    run_id = uuid4()
    collector = CollectingSink()
    hub = ObservabilityHub((FailingSink(), collector))

    hub.record_model_call(_model_event(run_id))
    hub.record_product_event(
        ProductTelemetryEvent(
            event_name="workflow transitioned",
            workflow_run_id=run_id,
        )
    )

    assert len(collector.model_events) == 1
    assert len(collector.product_events) == 1


def test_langfuse_uses_deterministic_run_trace_and_hides_model_io_by_default() -> None:
    run_id = uuid4()
    client = FakeLangfuseClient()
    sink = LangfuseTelemetrySink(
        public_key="public",
        secret_key="secret",
        base_url="https://langfuse.invalid",
        environment="test",
        capture_model_io=False,
        client=client,
    )

    sink.record_model_call(_model_event(run_id))
    sink.record_model_call(_model_event(run_id))
    sink.record_evaluation(
        EvaluationTelemetryEvent(
            workflow_run_id=run_id,
            name="factual_support",
            value=1.0,
            data_type="NUMERIC",
        )
    )

    assert client.trace_seeds == [str(run_id), str(run_id), str(run_id)]
    assert len(client.observations) == 2
    assert client.observations[0]["trace_context"] == {"trace_id": "a" * 32}
    assert "input" not in client.observations[0]
    assert "output" not in client.observations[0]
    assert client.observations[0]["usage_details"] == {
        "input": 12,
        "output": 8,
        "total": 20,
    }
    assert client.observations[0]["cost_details"] == {"total_cost": 0.012}
    assert client.scores[0]["trace_id"] == "a" * 32


def test_langfuse_opt_in_model_io_is_redacted() -> None:
    client = FakeLangfuseClient()
    sink = LangfuseTelemetrySink(
        public_key="public",
        secret_key="secret",
        base_url="https://langfuse.invalid",
        environment="test",
        capture_model_io=True,
        client=client,
    )

    sink.record_model_call(_model_event(uuid4()))

    observation = client.observations[0]
    assert "raw-secret" not in str(observation["input"])
    assert "super-secret-value" not in str(observation["output"])
    assert REDACTED in str(observation["input"])
    assert REDACTED in str(observation["output"])


def test_posthog_events_are_personless_correlated_and_redacted() -> None:
    run_id = uuid4()
    client = FakePostHogClient()
    sink = PostHogTelemetrySink(
        project_token="project-token",
        host="https://posthog.invalid",
        client=client,
    )

    sink.record_product_event(
        ProductTelemetryEvent(
            event_name="workflow transitioned",
            workflow_run_id=run_id,
            agent_id="content",
            properties={
                "status": "DRAFTED",
                "api_key": "raw-api-key",
            },
        )
    )

    event, distinct_id, properties = client.calls[0]
    assert event == "workflow transitioned"
    assert distinct_id == f"workflow:{run_id}"
    assert properties["workflow_run_id"] == str(run_id)
    assert properties["$process_person_profile"] is False
    assert properties["api_key"] == REDACTED


def test_api_middleware_returns_stable_request_and_workflow_correlation() -> None:
    run_id = uuid4()

    with TestClient(create_app()) as client:
        response = client.get(
            "/health",
            headers={
                "X-Request-ID": "req-fixed",
                "X-Workflow-Run-ID": str(run_id),
            },
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-fixed"
    assert response.headers["X-Correlation-ID"] == str(run_id)


def test_one_run_correlates_orchestrator_model_cost_and_latency() -> None:
    run_id = _create_run()
    collector = CollectingSink()
    hub = ObservabilityHub((collector,))

    engine = ObservedWorkflowEngine(
        PostgresWorkflowEngine(get_session_factory()),
        hub,
    )
    transition = engine.apply(
        run_id,
        WorkflowCommand(
            action_key=f"topic-{uuid4().hex}",
            action_type=WorkflowActionType.TOPIC_PROPOSED,
            actor_kind=AuditActorKind.SYSTEM,
            actor_id="test",
        ),
    )
    assert transition.status is WorkflowStatus.CANDIDATE

    fake = DeterministicFakeModel(
        ["model output"],
        input_tokens=21,
        output_tokens=13,
        cost_usd=Decimal("0.019"),
        latency_ms=27,
    )
    route = ModelRoute(
        name="primary",
        model="provider/model",
        max_call_cost_usd=Decimal("0.05"),
    )
    gateway = ModelGateway(
        fake,
        model_policy=ModelPolicy(
            routes={ModelTask.EDITORIAL_INTELLIGENCE: route}
        ),
        budget_policy=BudgetPolicy(
            per_run_usd=Decimal("1"),
            default_per_agent_usd=Decimal("1"),
        ),
        budget_ledger=BudgetLedger(get_session_factory()),
        observability=hub,
    )
    output = gateway.generate_text(
        ModelRequest(
            workflow_run_id=run_id,
            agent_id="editorial-intelligence",
            task=ModelTask.EDITORIAL_INTELLIGENCE,
            messages=[
                ModelMessage(
                    role=ModelRole.USER,
                    content="Analyze this signal.",
                )
            ],
        ),
        call_key=f"model-{uuid4().hex}",
    )

    assert output == "model output"
    assert collector.product_events[0].workflow_run_id == run_id
    assert collector.model_events[0].workflow_run_id == run_id
    assert collector.model_events[0].agent_id == "editorial-intelligence"
    assert collector.model_events[0].cost_usd == Decimal("0.019")
    assert collector.model_events[0].latency_ms == 27


def test_telemetry_outage_cannot_rollback_canonical_workflow_state() -> None:
    run_id = _create_run()
    engine = ObservedWorkflowEngine(
        PostgresWorkflowEngine(get_session_factory()),
        ObservabilityHub((FailingSink(),)),
    )

    result = engine.apply(
        run_id,
        WorkflowCommand(
            action_key=f"topic-{uuid4().hex}",
            action_type=WorkflowActionType.TOPIC_PROPOSED,
            actor_kind=AuditActorKind.SYSTEM,
            actor_id="test",
        ),
    )

    assert result.status is WorkflowStatus.CANDIDATE
    with get_session_factory()() as session:
        persisted = session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        assert persisted is not None
        assert persisted.status == WorkflowStatus.CANDIDATE.value
