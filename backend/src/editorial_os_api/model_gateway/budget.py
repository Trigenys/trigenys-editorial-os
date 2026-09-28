from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.model_gateway.contracts import (
    BudgetPolicy,
    ModelRequest,
    ModelRoute,
    RawModelResponse,
)
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import ModelUsageRecord, WorkflowRun


class BudgetExceededError(RuntimeError):
    pass


class DuplicateModelCallError(RuntimeError):
    pass


@dataclass(frozen=True)
class BudgetCompletion:
    within_budget: bool
    cost_usd: Decimal
    estimated: bool


class BudgetLedger:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def reserve(
        self,
        request: ModelRequest,
        route: ModelRoute,
        *,
        call_key: str,
        policy: BudgetPolicy,
    ) -> None:
        with self._session_factory.begin() as session:
            run = session.scalar(
                select(WorkflowRun)
                .where(WorkflowRun.id == request.workflow_run_id)
                .with_for_update()
            )
            if run is None:
                raise LookupError(str(request.workflow_run_id))

            existing = session.scalar(
                select(ModelUsageRecord).where(
                    ModelUsageRecord.workflow_run_id == request.workflow_run_id,
                    ModelUsageRecord.call_key == call_key,
                )
            )
            if existing is not None:
                raise DuplicateModelCallError(
                    f"Model call {call_key!r} already exists for run {request.workflow_run_id}."
                )

            records = list(
                session.scalars(
                    select(ModelUsageRecord).where(
                        ModelUsageRecord.workflow_run_id == request.workflow_run_id
                    )
                )
            )
            reservation = route.max_call_cost_usd
            run_spend = self._effective_spend(records)
            if run_spend + reservation > policy.per_run_usd:
                raise BudgetExceededError(
                    "Run model budget exceeded before provider call: "
                    f"{run_spend} + {reservation} > {policy.per_run_usd} USD."
                )

            agent_spend = self._effective_spend(
                record for record in records if record.agent_id == request.agent_id
            )
            agent_ceiling = policy.ceiling_for_agent(request.agent_id)
            if agent_spend + reservation > agent_ceiling:
                raise BudgetExceededError(
                    "Agent model budget exceeded before provider call: "
                    f"{agent_spend} + {reservation} > {agent_ceiling} USD."
                )

            session.add(
                ModelUsageRecord(
                    workflow_run_id=request.workflow_run_id,
                    agent_id=request.agent_id,
                    task=request.task.value,
                    call_key=call_key,
                    route_name=route.name,
                    provider_model=route.model,
                    status="RESERVED",
                    reserved_cost_usd=reservation,
                    actual_cost_usd=None,
                    cost_is_estimated=False,
                    input_tokens=None,
                    output_tokens=None,
                    latency_ms=None,
                    error_kind=None,
                    error_message=None,
                    created_at=utcnow(),
                    completed_at=None,
                )
            )

    def complete(
        self,
        workflow_run_id: UUID,
        *,
        call_key: str,
        response: RawModelResponse,
        policy: BudgetPolicy,
    ) -> BudgetCompletion:
        with self._session_factory.begin() as session:
            session.scalar(
                select(WorkflowRun)
                .where(WorkflowRun.id == workflow_run_id)
                .with_for_update()
            )
            record = session.scalar(
                select(ModelUsageRecord)
                .where(
                    ModelUsageRecord.workflow_run_id == workflow_run_id,
                    ModelUsageRecord.call_key == call_key,
                )
                .with_for_update()
            )
            if record is None:
                raise LookupError(call_key)
            if record.status != "RESERVED":
                raise RuntimeError(
                    f"Model call {call_key!r} cannot complete from status {record.status!r}."
                )

            estimated = response.cost_usd is None
            cost = response.cost_usd if response.cost_usd is not None else record.reserved_cost_usd

            others = list(
                session.scalars(
                    select(ModelUsageRecord).where(
                        ModelUsageRecord.workflow_run_id == workflow_run_id,
                        ModelUsageRecord.id != record.id,
                    )
                )
            )
            run_spend = self._effective_spend(others) + cost
            agent_spend = self._effective_spend(
                item for item in others if item.agent_id == record.agent_id
            ) + cost
            within_budget = (
                run_spend <= policy.per_run_usd
                and agent_spend <= policy.ceiling_for_agent(record.agent_id)
            )

            record.status = "COMPLETED" if within_budget else "COMPLETED_OVER_BUDGET"
            record.actual_cost_usd = cost
            record.cost_is_estimated = estimated
            record.input_tokens = response.input_tokens
            record.output_tokens = response.output_tokens
            record.latency_ms = response.latency_ms
            record.completed_at = utcnow()

            return BudgetCompletion(
                within_budget=within_budget,
                cost_usd=cost,
                estimated=estimated,
            )

    def fail(
        self,
        workflow_run_id: UUID,
        *,
        call_key: str,
        error: Exception,
    ) -> None:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(ModelUsageRecord)
                .where(
                    ModelUsageRecord.workflow_run_id == workflow_run_id,
                    ModelUsageRecord.call_key == call_key,
                )
                .with_for_update()
            )
            if record is None or record.status != "RESERVED":
                return

            record.status = "FAILED_ESTIMATED"
            record.actual_cost_usd = record.reserved_cost_usd
            record.cost_is_estimated = True
            record.error_kind = type(error).__name__
            record.error_message = str(error)[:2000]
            record.completed_at = utcnow()

    @staticmethod
    def _effective_spend(records: object) -> Decimal:
        total = Decimal("0")
        for record in records:
            assert isinstance(record, ModelUsageRecord)
            if record.status == "RESERVED":
                total += record.reserved_cost_usd
            elif record.actual_cost_usd is not None:
                total += record.actual_cost_usd
        return total
