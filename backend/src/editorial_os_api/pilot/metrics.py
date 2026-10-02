from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.persistence.models import (
    Claim,
    Draft,
    EditorialQAReview,
    GateDecision,
    ModelUsageRecord,
    Publication,
    WorkflowAction,
    WorkflowRun,
)


@dataclass(frozen=True)
class PilotRunMetrics:
    workflow_run_id: UUID
    status: str
    duration_seconds: float
    human_gate_touches: int
    retry_actions: int
    failure_actions: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    unsupported_claims: int
    contested_claims: int
    stale_claims: int
    qa_error_findings: int
    cms_publication_count: int
    cms_external_ids: tuple[str, ...]


@dataclass(frozen=True)
class PilotBatchMetrics:
    run_count: int
    completed_count: int
    total_human_gate_touches: int
    total_retry_actions: int
    total_failure_actions: int
    total_cost_usd: Decimal
    factual_defect_count: int
    duplicate_cms_external_id_count: int
    runs: tuple[PilotRunMetrics, ...]


class PilotMetricsService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def summarize_run(self, workflow_run_id: UUID) -> PilotRunMetrics:
        with self._session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise LookupError(str(workflow_run_id))

            gate_touches = session.scalar(
                select(func.count())
                .select_from(GateDecision)
                .where(GateDecision.workflow_run_id == workflow_run_id)
            ) or 0
            actions = list(
                session.scalars(
                    select(WorkflowAction).where(
                        WorkflowAction.workflow_run_id == workflow_run_id
                    )
                )
            )
            usages = list(
                session.scalars(
                    select(ModelUsageRecord).where(
                        ModelUsageRecord.workflow_run_id == workflow_run_id
                    )
                )
            )
            claims = list(
                session.scalars(
                    select(Claim).where(Claim.workflow_run_id == workflow_run_id)
                )
            )
            drafts = list(
                session.scalars(
                    select(Draft).where(Draft.workflow_run_id == workflow_run_id)
                )
            )
            reviews = list(
                session.scalars(
                    select(EditorialQAReview).where(
                        EditorialQAReview.workflow_run_id == workflow_run_id
                    )
                )
            )
            publications = list(
                session.scalars(
                    select(Publication).where(
                        Publication.workflow_run_id == workflow_run_id
                    )
                )
            )

        retry_actions = sum(
            item.action_type in {"RETRY", "RESUME"}
            for item in actions
        )
        failure_actions = sum(
            item.action_type in {
                "FAILURE_RETRYABLE",
                "FAILURE_TERMINAL",
                "BLOCK",
            }
            for item in actions
        )
        cost = Decimal("0")
        for item in usages:
            cost += (
                item.actual_cost_usd
                if item.actual_cost_usd is not None
                else item.reserved_cost_usd
            )
        unsupported_claims = sum(
            item.support_status == "UNSUPPORTED"
            for item in claims
        ) + sum(len(item.unsupported_factual_claims) for item in drafts)
        contested_claims = sum(item.contested for item in claims)
        stale_claims = sum(item.stale for item in claims)
        qa_error_findings = sum(
            1
            for review in reviews
            for finding in review.findings
            if finding.get("severity") in {"ERROR", "BLOCKER"}
        )
        external_ids = tuple(
            sorted(
                {
                    item.external_id
                    for item in publications
                    if item.external_id is not None
                }
            )
        )
        duration = max(
            0.0,
            (run.updated_at - run.created_at).total_seconds(),
        )

        return PilotRunMetrics(
            workflow_run_id=workflow_run_id,
            status=run.status,
            duration_seconds=duration,
            human_gate_touches=int(gate_touches),
            retry_actions=retry_actions,
            failure_actions=failure_actions,
            model_calls=len(usages),
            input_tokens=sum(item.input_tokens or 0 for item in usages),
            output_tokens=sum(item.output_tokens or 0 for item in usages),
            cost_usd=cost,
            unsupported_claims=unsupported_claims,
            contested_claims=contested_claims,
            stale_claims=stale_claims,
            qa_error_findings=qa_error_findings,
            cms_publication_count=len(publications),
            cms_external_ids=external_ids,
        )

    def summarize_batch(
        self,
        workflow_run_ids: list[UUID],
    ) -> PilotBatchMetrics:
        runs = tuple(self.summarize_run(run_id) for run_id in workflow_run_ids)
        all_external_ids = [
            external_id
            for run in runs
            for external_id in run.cms_external_ids
        ]
        duplicate_count = len(all_external_ids) - len(set(all_external_ids))
        factual_defects = sum(
            run.unsupported_claims
            + run.contested_claims
            + run.stale_claims
            + run.qa_error_findings
            for run in runs
        )
        return PilotBatchMetrics(
            run_count=len(runs),
            completed_count=sum(
                run.status
                in {"PUBLISHED", "DISTRIBUTED", "MEASURED"}
                for run in runs
            ),
            total_human_gate_touches=sum(
                run.human_gate_touches for run in runs
            ),
            total_retry_actions=sum(run.retry_actions for run in runs),
            total_failure_actions=sum(run.failure_actions for run in runs),
            total_cost_usd=sum(
                (run.cost_usd for run in runs),
                start=Decimal("0"),
            ),
            factual_defect_count=factual_defects,
            duplicate_cms_external_id_count=duplicate_count,
            runs=runs,
        )
