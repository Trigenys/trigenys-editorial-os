"""Extend topic candidates for explainable editorial intelligence.

Revision ID: 20260929_0006
Revises: 20260928_0005
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260929_0006"
down_revision: str | Sequence[str] | None = "20260928_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "topic_candidates",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "topic_candidates",
        sa.Column("cluster_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "topic_candidates",
        sa.Column("novelty_score", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "topic_candidates",
        sa.Column("relevance_score", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "topic_candidates",
        sa.Column(
            "source_diversity_score",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "topic_candidates",
        sa.Column("composite_score", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "topic_candidates",
        sa.Column(
            "proposed_format",
            sa.String(length=80),
            server_default="article",
            nullable=False,
        ),
    )
    op.add_column(
        "topic_candidates",
        sa.Column(
            "urgency",
            sa.String(length=20),
            server_default="NORMAL",
            nullable=False,
        ),
    )
    op.add_column(
        "topic_candidates",
        sa.Column(
            "source_item_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "topic_candidates",
        sa.Column(
            "reason_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE topic_candidates
        SET cluster_key = 'legacy:' || id::text
        WHERE cluster_key IS NULL
        """
    )
    op.alter_column("topic_candidates", "cluster_key", nullable=False)
    op.create_unique_constraint(
        "workflow_topic_cluster",
        "topic_candidates",
        ["workflow_run_id", "cluster_key"],
    )


def downgrade() -> None:
    op.drop_constraint("workflow_topic_cluster", "topic_candidates", type_="unique")
    op.drop_column("topic_candidates", "reason_details")
    op.drop_column("topic_candidates", "source_item_ids")
    op.drop_column("topic_candidates", "urgency")
    op.drop_column("topic_candidates", "proposed_format")
    op.drop_column("topic_candidates", "composite_score")
    op.drop_column("topic_candidates", "source_diversity_score")
    op.drop_column("topic_candidates", "relevance_score")
    op.drop_column("topic_candidates", "novelty_score")
    op.drop_column("topic_candidates", "cluster_key")
    op.drop_column("topic_candidates", "version")
