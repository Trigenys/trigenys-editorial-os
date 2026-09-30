"""Add structured Editorial QA reviews.

Revision ID: 20260930_0010
Revises: 20260930_0009
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260930_0010"
down_revision: str | Sequence[str] | None = "20260930_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "editorial_qa_reviews",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("manifest_version", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("confidence_class", sa.String(length=2), nullable=False),
        sa.Column("risk_class", sa.String(length=2), nullable=False),
        sa.Column("human_approval_required", sa.Boolean(), nullable=False),
        sa.Column("gate_b_ready", sa.Boolean(), nullable=False),
        sa.Column("adapter_name", sa.String(length=120), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column(
            "policy_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "findings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "subject_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_editorial_qa_reviews_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["drafts.id"],
            name=op.f("fk_editorial_qa_reviews_draft_id_drafts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id"],
            ["asset_manifests.id"],
            name=op.f("fk_editorial_qa_reviews_manifest_id_asset_manifests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_editorial_qa_reviews")),
        sa.UniqueConstraint(
            "workflow_run_id",
            "draft_id",
            "manifest_id",
            "input_fingerprint",
            name="workflow_qa_input_fingerprint",
        ),
        sa.UniqueConstraint(
            "workflow_run_id",
            "version",
            name="workflow_qa_review_version",
        ),
    )
    op.create_index(
        op.f("ix_editorial_qa_reviews_workflow_run_id"),
        "editorial_qa_reviews",
        ["workflow_run_id"],
    )
    op.create_index(
        op.f("ix_editorial_qa_reviews_draft_id"),
        "editorial_qa_reviews",
        ["draft_id"],
    )
    op.create_index(
        op.f("ix_editorial_qa_reviews_manifest_id"),
        "editorial_qa_reviews",
        ["manifest_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_editorial_qa_reviews_manifest_id"),
        table_name="editorial_qa_reviews",
    )
    op.drop_index(
        op.f("ix_editorial_qa_reviews_draft_id"),
        table_name="editorial_qa_reviews",
    )
    op.drop_index(
        op.f("ix_editorial_qa_reviews_workflow_run_id"),
        table_name="editorial_qa_reviews",
    )
    op.drop_table("editorial_qa_reviews")
