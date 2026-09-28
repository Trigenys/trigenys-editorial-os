from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from editorial_os_api.domain import (
    ConfidenceClass,
    GateDecisionContract,
    GateKind,
    GateOutcome,
    RiskClass,
    WorkflowRunContract,
    WorkflowStatus,
)


def test_contracts_forbid_provider_specific_extra_state() -> None:
    now = datetime.now(timezone.utc)

    with pytest.raises(ValidationError):
        WorkflowRunContract(
            id=uuid4(),
            vertical_key="fixture",
            vertical_version="1",
            status=WorkflowStatus.INGESTED,
            risk_class=RiskClass.R0,
            confidence_class=ConfidenceClass.C0,
            policy_version="1",
            idempotency_key="fixture-run",
            created_at=now,
            updated_at=now,
            provider_sdk_object={"vendor": "should-not-cross-boundary"},
        )


def test_gate_decision_is_bound_to_an_artifact_version() -> None:
    now = datetime.now(timezone.utc)
    artifact_id = uuid4()

    decision = GateDecisionContract(
        id=uuid4(),
        workflow_run_id=uuid4(),
        gate=GateKind.EDITORIAL,
        outcome=GateOutcome.APPROVED,
        artifact_type="draft",
        artifact_id=artifact_id,
        artifact_version=3,
        actor_id="operator",
        decided_at=now,
    )

    assert decision.artifact_id == artifact_id
    assert decision.artifact_version == 3
