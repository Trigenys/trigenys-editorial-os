from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from editorial_os_api.config import get_settings
from editorial_os_api.domain.enums import (
    AuditActorKind,
    GateKind,
    GateOutcome,
    RiskClass,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.orchestration.engine import (
    IdempotencyConflictError,
    InvalidTransitionError,
    PostgresWorkflowEngine,
)
from editorial_os_api.orchestration.langgraph import (
    LangGraphGateCoordinator,
    postgres_checkpointer,
)
from editorial_os_api.orchestration.models import GateResume, WorkflowCommand
from editorial_os_api.orchestration.policy import GatePolicy
from editorial_os_api.persistence.models import WorkflowAction, WorkflowRun
from editorial_os_api.persistence.session import get_session_factory

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _create_run(
    *,
    status: WorkflowStatus = WorkflowStatus.INGESTED,
    vertical_key: str = "fixture",
    risk_class: RiskClass = RiskClass.R0,
) -> UUID:
    _upgrade_schema()
    factory = get_session_factory()
    run = WorkflowRun(
        vertical_key=vertical_key,
        vertical_version="1",
        status=status.value,
        risk_class=risk_class.value,
        confidence_class="C0",
        policy_version="1",
        idempotency_key=f"run-{uuid4().hex}",
        context={},
    )
    with factory.begin() as session:
        session.add(run)
        session.flush()
        run_id = run.id
    return run_id


def _command(
    action_type: WorkflowActionType,
    *,
    action_key: str | None = None,
    payload: dict[str, object] | None = None,
) -> WorkflowCommand:
    return WorkflowCommand(
        action_key=action_key or f"{action_type.value.lower()}-{uuid4().hex}",
        action_type=action_type,
        actor_kind=AuditActorKind.SYSTEM,
        actor_id="test-system",
        payload=payload or {},
    )


def _gate_resume(outcome: GateOutcome = GateOutcome.APPROVED) -> GateResume:
    return GateResume(
        action_key=f"gate-{uuid4().hex}",
        outcome=outcome,
        actor_id="test-operator",
        artifact_type="fixture",
        artifact_id=uuid4(),
        artifact_version=1,
    )


def test_happy_path_reaches_measured_only_through_three_gates() -> None:
    run_id = _create_run()
    engine = PostgresWorkflowEngine(get_session_factory())

    assert engine.apply(run_id, _command(WorkflowActionType.TOPIC_PROPOSED)).pending_gate == "A"
    assert engine.decide_gate(run_id, GateKind.TOPIC, _gate_resume()).status is (
        WorkflowStatus.TOPIC_APPROVED
    )
    assert engine.apply(
        run_id,
        _command(WorkflowActionType.VERIFICATION_COMPLETED),
    ).status is WorkflowStatus.VERIFIED
    assert engine.apply(
        run_id,
        _command(WorkflowActionType.DRAFT_COMPLETED),
    ).status is WorkflowStatus.DRAFTED
    assert engine.apply(
        run_id,
        _command(WorkflowActionType.ASSETS_COMPLETED),
    ).status is WorkflowStatus.ASSETS_READY
    assert engine.apply(run_id, _command(WorkflowActionType.QA_PASSED)).pending_gate == "B"
    assert engine.decide_gate(run_id, GateKind.EDITORIAL, _gate_resume()).status is (
        WorkflowStatus.EDITORIAL_APPROVED
    )
    assert engine.apply(run_id, _command(WorkflowActionType.PACKAGE_READY)).pending_gate == "C"
    assert engine.decide_gate(run_id, GateKind.PUBLISH, _gate_resume()).status is (
        WorkflowStatus.PUBLISH_APPROVED
    )
    assert engine.apply(
        run_id,
        _command(WorkflowActionType.PUBLICATION_COMPLETED),
    ).status is WorkflowStatus.PUBLISHED
    assert engine.apply(
        run_id,
        _command(WorkflowActionType.DISTRIBUTION_COMPLETED),
    ).status is WorkflowStatus.DISTRIBUTED
    final = engine.apply(
        run_id,
        _command(WorkflowActionType.MEASUREMENT_CAPTURED),
    )

    assert final.status is WorkflowStatus.MEASURED
    assert final.state_version == 12
    assert final.pending_gate is None


def test_invalid_transition_fails_closed_without_writing_action() -> None:
    run_id = _create_run()
    engine = PostgresWorkflowEngine(get_session_factory())

    with pytest.raises(InvalidTransitionError):
        engine.apply(run_id, _command(WorkflowActionType.DRAFT_COMPLETED))

    with get_session_factory()() as session:
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        assert run.status == WorkflowStatus.INGESTED.value
        count = session.scalar(
            select(func.count())
            .select_from(WorkflowAction)
            .where(WorkflowAction.workflow_run_id == run_id)
        )
        assert count == 0


def test_duplicate_delivery_is_a_noop_and_conflicting_reuse_fails() -> None:
    run_id = _create_run()
    engine = PostgresWorkflowEngine(get_session_factory())
    action_key = f"topic-{uuid4().hex}"
    original = _command(
        WorkflowActionType.TOPIC_PROPOSED,
        action_key=action_key,
        payload={"source_event": "evt-1"},
    )

    first = engine.apply(run_id, original)
    second = engine.apply(run_id, original)

    assert first.applied is True
    assert second.applied is False
    assert second.status is WorkflowStatus.CANDIDATE
    assert second.state_version == 1

    conflicting = _command(
        WorkflowActionType.TOPIC_PROPOSED,
        action_key=action_key,
        payload={"source_event": "different"},
    )
    with pytest.raises(IdempotencyConflictError):
        engine.apply(run_id, conflicting)


def test_qa_revision_action_routes_assets_ready_back_to_drafting() -> None:
    run_id = _create_run(status=WorkflowStatus.ASSETS_READY)
    engine = PostgresWorkflowEngine(get_session_factory())

    result = engine.apply(
        run_id,
        _command(WorkflowActionType.QA_REVISION_REQUIRED),
    )

    assert result.status is WorkflowStatus.DRAFTED
    assert result.pending_gate is None


def test_gate_b_revision_routes_back_to_drafting() -> None:
    run_id = _create_run(status=WorkflowStatus.QA_PASSED)
    engine = PostgresWorkflowEngine(get_session_factory())

    result = engine.decide_gate(
        run_id,
        GateKind.EDITORIAL,
        _gate_resume(GateOutcome.REVISION_REQUESTED),
    )

    assert result.status is WorkflowStatus.DRAFTED
    assert result.pending_gate is None


def test_each_gate_blocks_the_next_expensive_or_remote_step() -> None:
    engine = PostgresWorkflowEngine(get_session_factory())

    gate_a_run = _create_run(status=WorkflowStatus.CANDIDATE)
    with pytest.raises(InvalidTransitionError):
        engine.apply(
            gate_a_run,
            _command(WorkflowActionType.VERIFICATION_COMPLETED),
        )

    gate_b_run = _create_run(status=WorkflowStatus.QA_PASSED)
    with pytest.raises(InvalidTransitionError):
        engine.apply(gate_b_run, _command(WorkflowActionType.PACKAGE_READY))

    gate_c_run = _create_run(status=WorkflowStatus.READY_TO_PUBLISH)
    with pytest.raises(InvalidTransitionError):
        engine.apply(
            gate_c_run,
            _command(WorkflowActionType.PUBLICATION_COMPLETED),
        )


def test_retryable_failure_survives_engine_restart() -> None:
    run_id = _create_run(status=WorkflowStatus.DRAFTED)
    first_engine = PostgresWorkflowEngine(get_session_factory())

    failed = first_engine.apply(
        run_id,
        _command(WorkflowActionType.FAILURE_RETRYABLE),
    )
    assert failed.status is WorkflowStatus.FAILED_RETRYABLE

    second_engine = PostgresWorkflowEngine(get_session_factory())
    resumed = second_engine.apply(run_id, _command(WorkflowActionType.RETRY))

    assert resumed.status is WorkflowStatus.DRAFTED


def test_gate_policy_can_vary_by_vertical_and_risk_outside_mvp_lock() -> None:
    policy = GatePolicy(
        mvp_lock=False,
        required_by_default=frozenset({GateKind.PUBLISH}),
        vertical_required={
            "strict": frozenset({GateKind.TOPIC}),
        },
        risk_required={
            RiskClass.R2: frozenset({GateKind.TOPIC, GateKind.EDITORIAL}),
        },
    )
    engine = PostgresWorkflowEngine(get_session_factory(), policy=policy)

    fast_run = _create_run(status=WorkflowStatus.CANDIDATE, vertical_key="fast")
    assert engine.pending_gate(fast_run) is None
    assert engine.apply(
        fast_run,
        _command(WorkflowActionType.VERIFICATION_COMPLETED),
    ).status is WorkflowStatus.VERIFIED

    strict_run = _create_run(status=WorkflowStatus.CANDIDATE, vertical_key="strict")
    assert engine.pending_gate(strict_run) is GateKind.TOPIC

    sensitive_run = _create_run(
        status=WorkflowStatus.QA_PASSED,
        vertical_key="fast",
        risk_class=RiskClass.R2,
    )
    assert engine.pending_gate(sensitive_run) is GateKind.EDITORIAL


def test_langgraph_gate_pause_resumes_after_coordinator_restart() -> None:
    run_id = _create_run(status=WorkflowStatus.CANDIDATE)
    engine = PostgresWorkflowEngine(get_session_factory())
    database_url = get_settings().database_url

    with postgres_checkpointer(database_url) as checkpointer:
        first = LangGraphGateCoordinator(engine, checkpointer)
        paused = first.pause_for_gate(run_id)
        assert "__interrupt__" in paused

    with postgres_checkpointer(database_url) as checkpointer:
        second = LangGraphGateCoordinator(engine, checkpointer)
        resumed = second.resume_gate(run_id, _gate_resume())

    result = resumed["result"]
    assert isinstance(result, dict)
    assert result["status"] == WorkflowStatus.TOPIC_APPROVED.value
