"""Add research verification ledger metadata and research briefs.

Revision ID: 20260929_0007
Revises: 20260929_0006
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260929_0007"
down_revision: str | Sequence[str] | None = "20260929_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_items",
        sa.Column(
            "source_role",
            sa.String(length=20),
            server_default="SECONDARY",
            nullable=False,
        ),
    )
    op.add_column(
        "evidence_items",
        sa.Column("stale", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "extraction_method",
            sa.String(length=80),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.add_column("claims", sa.Column("claim_key", sa.String(length=128)))
    op.execute(
        """
        UPDATE claims
        SET claim_key = 'legacy:' || id::text
        WHERE claim_key IS NULL
        """
    )
    op.alter_column("claims", "claim_key", nullable=False)
    op.add_column(
        "claims",
        sa.Column(
            "confidence_reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "claims",
        sa.Column(
            "support_status",
            sa.String(length=20),
            server_default="UNKNOWN",
            nullable=False,
        ),
    )
    op.add_column(
        "claims",
        sa.Column("stale", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_unique_constraint(
        "workflow_claim_key",
        "claims",
        ["workflow_run_id", "claim_key"],
    )

    op.add_column(
        "claim_evidence_links",
        sa.Column(
            "stance",
            sa.String(length=20),
            server_default="SUPPORTS",
            nullable=False,
        ),
    )
    op.add_column(
        "claim_evidence_links",
        sa.Column("reason_code", sa.String(length=120)),
    )

    op.create_table(
        "research_briefs",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("topic_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("confidence_class", sa.String(length=2), nullable=False),
        sa.Column("risk_class", sa.String(length=2), nullable=False),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "claim_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "contradiction_claim_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "unsupported_claim_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "stale_claim_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "source_plan",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "budget_usage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "review_required",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("review_resolved_by", sa.String(length=255)),
        sa.Column("review_resolved_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["topic_candidate_id"],
            ["topic_candidates.id"],
            name=op.f("fk_research_briefs_topic_candidate_id_topic_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_research_briefs_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_briefs")),
        sa.UniqueConstraint(
            "workflow_run_id",
            "version",
            name="workflow_research_brief_version",
        ),
        sa.UniqueConstraint(
            "workflow_run_id",
            "input_fingerprint",
            name="workflow_research_input_fingerprint",
        ),
    )
    op.create_index(
        op.f("ix_research_briefs_workflow_run_id"),
        "research_briefs",
        ["workflow_run_id"],
    )
    op.create_index(
        op.f("ix_research_briefs_topic_candidate_id"),
        "research_briefs",
        ["topic_candidate_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_research_briefs_topic_candidate_id"),
        table_name="research_briefs",
    )
    op.drop_index(
        op.f("ix_research_briefs_workflow_run_id"),
        table_name="research_briefs",
    )
    op.drop_table("research_briefs")

    op.drop_column("claim_evidence_links", "reason_code")
    op.drop_column("claim_evidence_links", "stance")

    op.drop_constraint("workflow_claim_key", "claims", type_="unique")
    op.drop_column("claims", "stale")
    op.drop_column("claims", "support_status")
    op.drop_column("claims", "confidence_reason_codes")
    op.drop_column("claims", "claim_key")

    op.drop_column("evidence_items", "metadata")
    op.drop_column("evidence_items", "extraction_method")
    op.drop_column("evidence_items", "stale")
    op.drop_column("evidence_items", "source_role")
