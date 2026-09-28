from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import BaseModel
from sqlalchemy import select

from editorial_os_api.model_gateway import (
    BudgetExceededError,
    BudgetLedger,
    BudgetPolicy,
    ModelGateway,
    ModelMessage,
    ModelPolicy,
    ModelRequest,
    ModelRole,
    ModelRoute,
    ModelTask,
    StructuredOutputError,
)
from editorial_os_api.model_gateway.adapters import LiteLLMClient
from editorial_os_api.model_gateway.fake import DeterministicFakeModel
from editorial_os_api.persistence.models import ModelUsageRecord, WorkflowRun
from editorial_os_api.persistence.session import get_session_factory

BACKEND_DIR = Path(__file__).resolve().parents[1]


class TopicOutput(BaseModel):
    title: str
    score: int


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _create_run() -> UUID:
    _upgrade_schema()
    run = WorkflowRun(
        vertical_key="fixture",
        vertical_version="1",
        status="INGESTED",
        risk_class="R0",
        confidence_class="C0",
        policy_version="1",
        idempotency_key=f"model-run-{uuid4().hex}",
        context={},
    )
    with get_session_factory().begin() as session:
        session.add(run)
        session.flush()
        run_id = run.id
    return run_id


def _route(
    *,
    name: str = "primary",
    model: str = "provider/model",
    max_call_cost_usd: Decimal = Decimal("0.05"),
) -> ModelRoute:
    return ModelRoute(
        name=name,
        model=model,
        max_call_cost_usd=max_call_cost_usd,
        supports_json_mode=True,
    )


def _request(run_id: UUID, *, agent_id: str = "editorial-intelligence") -> ModelRequest:
    return ModelRequest(
        workflow_run_id=run_id,
        agent_id=agent_id,
        task=ModelTask.EDITORIAL_INTELLIGENCE,
        messages=[
            ModelMessage(
                role=ModelRole.USER,
                content="Return a topic candidate.",
            )
        ],
    )


def _gateway(
    run_id: UUID,
    fake: DeterministicFakeModel,
    *,
    route: ModelRoute | None = None,
    budget: BudgetPolicy | None = None,
    max_repair_attempts: int = 1,
) -> ModelGateway:
    selected_route = route or _route()
    return ModelGateway(
        fake,
        model_policy=ModelPolicy(
            routes={
                ModelTask.EDITORIAL_INTELLIGENCE: selected_route,
            }
        ),
        budget_policy=budget
        or BudgetPolicy(
            per_run_usd=Decimal("1.00"),
            default_per_agent_usd=Decimal("0.50"),
        ),
        budget_ledger=BudgetLedger(get_session_factory()),
        max_repair_attempts=max_repair_attempts,
    )


def test_fake_model_runs_structured_ci_path_and_records_usage() -> None:
    run_id = _create_run()
    fake = DeterministicFakeModel(
        ['{"title":"A verified topic","score":91}'],
        input_tokens=17,
        output_tokens=9,
        cost_usd=Decimal("0.0123"),
        latency_ms=8,
    )
    gateway = _gateway(run_id, fake)

    output = gateway.generate_structured(
        _request(run_id),
        TopicOutput,
        call_key=f"topic-{uuid4().hex}",
    )

    assert output == TopicOutput(title="A verified topic", score=91)
    assert len(fake.calls) == 1

    with get_session_factory()() as session:
        usage = session.scalar(
            select(ModelUsageRecord).where(ModelUsageRecord.workflow_run_id == run_id)
        )
        assert usage is not None
        assert usage.agent_id == "editorial-intelligence"
        assert usage.task == ModelTask.EDITORIAL_INTELLIGENCE.value
        assert usage.input_tokens == 17
        assert usage.output_tokens == 9
        assert usage.actual_cost_usd == Decimal("0.012300")
        assert usage.latency_ms == 8
        assert usage.status == "COMPLETED"


def test_invalid_structured_output_gets_one_bounded_repair() -> None:
    run_id = _create_run()
    fake = DeterministicFakeModel(
        [
            '{"title":"Missing score"}',
            '{"title":"Repaired","score":88}',
        ],
        cost_usd=Decimal("0.01"),
    )
    gateway = _gateway(run_id, fake)

    output = gateway.generate_structured(
        _request(run_id),
        TopicOutput,
        call_key=f"repair-{uuid4().hex}",
    )

    assert output.score == 88
    assert len(fake.calls) == 2
    repair_messages = fake.calls[1][0].messages
    assert any("corrected JSON only" in message.content for message in repair_messages)

    with get_session_factory()() as session:
        usage = list(
            session.scalars(
                select(ModelUsageRecord).where(ModelUsageRecord.workflow_run_id == run_id)
            )
        )
        assert len(usage) == 2
        assert sum(item.actual_cost_usd or Decimal("0") for item in usage) == Decimal("0.02")


def test_invalid_structured_output_fails_closed_after_repair_budget() -> None:
    run_id = _create_run()
    fake = DeterministicFakeModel(
        [
            "not-json",
            '{"still":"wrong"}',
        ]
    )
    gateway = _gateway(run_id, fake)

    with pytest.raises(StructuredOutputError):
        gateway.generate_structured(
            _request(run_id),
            TopicOutput,
            call_key=f"invalid-{uuid4().hex}",
        )

    assert len(fake.calls) == 2


def test_run_budget_breach_prevents_provider_call() -> None:
    run_id = _create_run()
    fake = DeterministicFakeModel(['{"title":"Should not run","score":1}'])
    route = _route(max_call_cost_usd=Decimal("0.20"))
    budget = BudgetPolicy(
        per_run_usd=Decimal("0.10"),
        default_per_agent_usd=Decimal("1.00"),
    )
    gateway = _gateway(run_id, fake, route=route, budget=budget)

    with pytest.raises(BudgetExceededError):
        gateway.generate_structured(
            _request(run_id),
            TopicOutput,
            call_key=f"over-budget-{uuid4().hex}",
        )

    assert fake.calls == []


def test_agent_budget_is_enforced_independently_from_run_budget() -> None:
    run_id = _create_run()
    fake = DeterministicFakeModel(
        [
            '{"title":"First","score":1}',
            '{"title":"Second","score":2}',
        ],
        cost_usd=Decimal("0.05"),
    )
    route = _route(max_call_cost_usd=Decimal("0.10"))
    budget = BudgetPolicy(
        per_run_usd=Decimal("1.00"),
        default_per_agent_usd=Decimal("0.12"),
    )
    gateway = _gateway(run_id, fake, route=route, budget=budget)
    request = _request(run_id)

    gateway.generate_structured(
        request,
        TopicOutput,
        call_key=f"agent-first-{uuid4().hex}",
    )

    with pytest.raises(BudgetExceededError):
        gateway.generate_structured(
            request,
            TopicOutput,
            call_key=f"agent-second-{uuid4().hex}",
        )

    assert len(fake.calls) == 1


def test_actual_cost_above_reservation_is_recorded_and_output_is_withheld() -> None:
    run_id = _create_run()
    fake = DeterministicFakeModel(
        ['{"title":"Expensive","score":1}'],
        cost_usd=Decimal("0.30"),
    )
    route = _route(max_call_cost_usd=Decimal("0.20"))
    budget = BudgetPolicy(
        per_run_usd=Decimal("0.25"),
        default_per_agent_usd=Decimal("0.25"),
    )
    gateway = _gateway(run_id, fake, route=route, budget=budget)

    with pytest.raises(BudgetExceededError):
        gateway.generate_structured(
            _request(run_id),
            TopicOutput,
            call_key=f"actual-over-{uuid4().hex}",
        )

    with get_session_factory()() as session:
        usage = session.scalar(
            select(ModelUsageRecord).where(ModelUsageRecord.workflow_run_id == run_id)
        )
        assert usage is not None
        assert usage.status == "COMPLETED_OVER_BUDGET"
        assert usage.actual_cost_usd == Decimal("0.300000")


def test_litellm_adapter_accepts_two_provider_routes_without_paid_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_models: list[str] = []

    def fake_completion(**kwargs: object) -> SimpleNamespace:
        model = str(kwargs["model"])
        seen_models.append(model)
        return SimpleNamespace(
            model=model,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"title":"Portable","score":99}')
                )
            ],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
            _hidden_params={"response_cost": 0.001},
        )

    monkeypatch.setattr(
        "editorial_os_api.model_gateway.adapters.litellm.litellm.completion",
        fake_completion,
    )

    client = LiteLLMClient()
    run_id = uuid4()
    request = _request(run_id)
    routes = [
        _route(name="openai-route", model="openai/gpt-5.6-terra"),
        _route(name="anthropic-route", model="anthropic/claude-sonnet-5"),
    ]

    responses = [
        client.complete(request, route, json_schema={"type": "object"})
        for route in routes
    ]

    assert [response.model for response in responses] == [route.model for route in routes]
    assert seen_models == [route.model for route in routes]


def test_vendor_sdk_import_is_isolated_to_adapter() -> None:
    source_root = BACKEND_DIR / "src" / "editorial_os_api"
    offenders: list[str] = []

    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root).as_posix()
        if relative == "model_gateway/adapters/litellm.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "import litellm" in text or "from litellm" in text:
            offenders.append(relative)

    assert offenders == []
