"""Add model usage and budget ledger.

Revision ID: 20260928_0004
Revises: 20260928_0003
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_0004"
down_revision: str | Sequence[str] | None = "20260928_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_usage_records",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.String(length=120), nullable=False),
        sa.Column("task", sa.String(length=80), nullable=False),
        sa.Column("call_key", sa.String(length=255), nullable=False),
        sa.Column("route_name", sa.String(length=120), nullable=False),
        sa.Column("provider_model", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reserved_cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("actual_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("cost_is_estimated", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_kind", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_model_usage_records_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_usage_records")),
        sa.UniqueConstraint(
            "workflow_run_id",
            "call_key",
            name="model_usage_call_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_model_usage_records_agent_id"),
        "model_usage_records",
        ["agent_id"],
    )
    op.create_index(
        op.f("ix_model_usage_records_workflow_run_id"),
        "model_usage_records",
        ["workflow_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_model_usage_records_workflow_run_id"),
        table_name="model_usage_records",
    )
    op.drop_index(
        op.f("ix_model_usage_records_agent_id"),
        table_name="model_usage_records",
    )
    op.drop_table("model_usage_records")
