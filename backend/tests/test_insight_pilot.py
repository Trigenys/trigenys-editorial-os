from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from editorial_os_api.persistence.models import (
    ModelUsageRecord,
    Source,
)
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.pilot import (
    APPROVED_SOURCES,
    INSIGHT_VERTICAL_KEY,
    INSIGHT_VERTICAL_VERSION,
    PILOT_SCENARIOS,
    PilotMetricsService,
    seed_approved_sources,
)
from editorial_os_api.vertical_packs import get_builtin_vertical_pack
from tests.factories import create_complete_workflow

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def test_insight_pilot_pack_and_scenarios_are_versioned_and_representative() -> None:
    pack = get_builtin_vertical_pack(
        INSIGHT_VERTICAL_KEY,
        INSIGHT_VERTICAL_VERSION,
    )

    assert pack.metadata["kind"] == "staging-pilot"
    assert pack.metadata["publication_mode"] == "payload-staging-only"
    assert pack.visual.assets_required is True
    assert set(pack.locales) == {"fr", "en"}
    assert len(PILOT_SCENARIOS) == 10
    assert len({scenario.key for scenario in PILOT_SCENARIOS}) == 10

    approved_keys = {source.key for source in APPROVED_SOURCES}
    assert 4 <= len(approved_keys) <= 8
    for scenario in PILOT_SCENARIOS:
        assert scenario.locale in pack.locales
        assert scenario.content_format in pack.formats
        assert set(scenario.source_keys).issubset(approved_keys)
        assert scenario.tags


def test_approved_source_seed_is_idempotent() -> None:
    _upgrade_schema()
    first = seed_approved_sources(get_session_factory())
    second = seed_approved_sources(get_session_factory())

    assert first == second
    assert set(first) == {source.key for source in APPROVED_SOURCES}

    with get_session_factory()() as session:
        count = session.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.vertical_keys.contains([INSIGHT_VERTICAL_KEY]))
        )
        pilot_rows = list(
            session.scalars(
                select(Source).where(
                    Source.vertical_keys.contains([INSIGHT_VERTICAL_KEY])
                )
            )
        )

    assert count == len(APPROVED_SOURCES)
    assert len(pilot_rows) == len(APPROVED_SOURCES)
    assert all(row.config["pilot_id"] == "insight-e2e-2026-10" for row in pilot_rows)


def test_pilot_metrics_capture_human_touches_cost_and_duplicate_safety() -> None:
    _upgrade_schema()
    with get_session_factory()() as session:
        first = create_complete_workflow(
            session,
            suffix=f"pilot-{uuid4().hex}",
        )
        second = create_complete_workflow(
            session,
            suffix=f"pilot-{uuid4().hex}",
        )

    with get_session_factory().begin() as session:
        session.add_all(
            [
                ModelUsageRecord(
                    workflow_run_id=first.workflow.id,
                    agent_id="content",
                    task="draft",
                    call_key=f"pilot-call-{uuid4().hex}",
                    route_name="pilot",
                    provider_model="fixture/model",
                    status="SUCCEEDED",
                    reserved_cost_usd=Decimal("0.020000"),
                    actual_cost_usd=Decimal("0.015000"),
                    cost_is_estimated=False,
                    input_tokens=1200,
                    output_tokens=600,
                    latency_ms=900,
                ),
                ModelUsageRecord(
                    workflow_run_id=second.workflow.id,
                    agent_id="creative",
                    task="visual",
                    call_key=f"pilot-call-{uuid4().hex}",
                    route_name="pilot",
                    provider_model="fixture/model",
                    status="SUCCEEDED",
                    reserved_cost_usd=Decimal("0.030000"),
                    actual_cost_usd=Decimal("0.025000"),
                    cost_is_estimated=False,
                    input_tokens=800,
                    output_tokens=300,
                    latency_ms=1200,
                ),
            ]
        )

    metrics = PilotMetricsService(get_session_factory()).summarize_batch(
        [first.workflow.id, second.workflow.id]
    )

    assert metrics.run_count == 2
    assert metrics.completed_count == 2
    assert metrics.total_human_gate_touches == 6
    assert metrics.total_cost_usd == Decimal("0.040000")
    assert metrics.duplicate_cms_external_id_count == 0
    assert sum(run.model_calls for run in metrics.runs) == 2
    assert sum(run.input_tokens for run in metrics.runs) == 2000
    assert sum(run.output_tokens for run in metrics.runs) == 900
