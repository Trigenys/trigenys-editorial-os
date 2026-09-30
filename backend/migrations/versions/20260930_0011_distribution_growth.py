"""Add distribution growth performance mapping.

Revision ID: 20260930_0011
Revises: 20260930_0010
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260930_0011"
down_revision: str | Sequence[str] | None = "20260930_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "performance_snapshots",
        sa.Column("topic_candidate_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "performance_snapshots",
        sa.Column(
            "provider",
            sa.String(length=80),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "performance_snapshots",
        sa.Column("event_key", sa.String(length=255), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_performance_snapshots_topic_candidate_id_topic_candidates"),
        "performance_snapshots",
        "topic_candidates",
        ["topic_candidate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_performance_snapshots_topic_candidate_id"),
        "performance_snapshots",
        ["topic_candidate_id"],
    )
    op.create_index(
        op.f("ix_performance_snapshots_event_key"),
        "performance_snapshots",
        ["event_key"],
    )
    op.create_unique_constraint(
        "performance_snapshot_event",
        "performance_snapshots",
        ["workflow_run_id", "event_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "performance_snapshot_event",
        "performance_snapshots",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_performance_snapshots_event_key"),
        table_name="performance_snapshots",
    )
    op.drop_index(
        op.f("ix_performance_snapshots_topic_candidate_id"),
        table_name="performance_snapshots",
    )
    op.drop_constraint(
        op.f("fk_performance_snapshots_topic_candidate_id_topic_candidates"),
        "performance_snapshots",
        type_="foreignkey",
    )
    op.drop_column("performance_snapshots", "event_key")
    op.drop_column("performance_snapshots", "provider")
    op.drop_column("performance_snapshots", "topic_candidate_id")
