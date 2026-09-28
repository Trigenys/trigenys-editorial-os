"""Add durable workflow action ledger and LangGraph checkpoint schema.

Revision ID: 20260928_0003
Revises: 20260928_0002
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260928_0003"
down_revision: str | Sequence[str] | None = "20260928_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column(
            "state_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("resume_status", sa.String(length=40), nullable=True),
    )

    op.create_table(
        "workflow_actions",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("action_key", sa.String(length=255), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("actor_kind", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=False),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("from_state_version", sa.Integer(), nullable=False),
        sa.Column("to_state_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_workflow_actions_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_actions")),
        sa.UniqueConstraint(
            "workflow_run_id",
            "action_key",
            name="workflow_action_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_workflow_actions_workflow_run_id"),
        "workflow_actions",
        ["workflow_run_id"],
    )

    op.execute(
        """
        CREATE TRIGGER workflow_actions_append_only
        BEFORE UPDATE OR DELETE ON workflow_actions
        FOR EACH ROW EXECUTE FUNCTION editorial_os_reject_append_only_mutation();
        """
    )

    op.execute("CREATE SCHEMA IF NOT EXISTS langgraph")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS langgraph CASCADE")
    op.execute("DROP TRIGGER IF EXISTS workflow_actions_append_only ON workflow_actions")
    op.drop_index(
        op.f("ix_workflow_actions_workflow_run_id"),
        table_name="workflow_actions",
    )
    op.drop_table("workflow_actions")
    op.drop_column("workflow_runs", "resume_status")
    op.drop_column("workflow_runs", "state_version")
