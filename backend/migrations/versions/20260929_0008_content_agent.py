"""Extend drafts for Content Agent provenance and vertical packs.

Revision ID: 20260929_0008
Revises: 20260929_0007
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260929_0008"
down_revision: str | Sequence[str] | None = "20260929_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "drafts",
        sa.Column("research_brief_id", sa.Uuid()),
    )
    op.add_column(
        "drafts",
        sa.Column("revision_of_id", sa.Uuid()),
    )
    op.add_column(
        "drafts",
        sa.Column(
            "content_format",
            sa.String(length=80),
            server_default="article",
            nullable=False,
        ),
    )
    op.add_column(
        "drafts",
        sa.Column(
            "vertical_pack_key",
            sa.String(length=120),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "drafts",
        sa.Column(
            "vertical_pack_version",
            sa.String(length=80),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "drafts",
        sa.Column("input_fingerprint", sa.String(length=128)),
    )
    op.execute(
        """
        UPDATE drafts
        SET input_fingerprint = 'legacy:' || id::text
        WHERE input_fingerprint IS NULL
        """
    )
    op.alter_column("drafts", "input_fingerprint", nullable=False)
    op.add_column(
        "drafts",
        sa.Column(
            "sections",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "drafts",
        sa.Column(
            "seo_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "drafts",
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "drafts",
        sa.Column(
            "internal_link_suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "drafts",
        sa.Column(
            "unsupported_factual_claims",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "drafts",
        sa.Column(
            "vertical_pack_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "drafts",
        sa.Column("revision_feedback", sa.Text()),
    )

    op.create_foreign_key(
        op.f("fk_drafts_research_brief_id_research_briefs"),
        "drafts",
        "research_briefs",
        ["research_brief_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_drafts_revision_of_id_drafts"),
        "drafts",
        "drafts",
        ["revision_of_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_drafts_research_brief_id"),
        "drafts",
        ["research_brief_id"],
    )
    op.create_index(
        op.f("ix_drafts_revision_of_id"),
        "drafts",
        ["revision_of_id"],
    )
    op.create_unique_constraint(
        "workflow_draft_input_fingerprint",
        "drafts",
        ["workflow_run_id", "locale", "input_fingerprint"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "workflow_draft_input_fingerprint",
        "drafts",
        type_="unique",
    )
    op.drop_index(op.f("ix_drafts_revision_of_id"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_research_brief_id"), table_name="drafts")
    op.drop_constraint(
        op.f("fk_drafts_revision_of_id_drafts"),
        "drafts",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_drafts_research_brief_id_research_briefs"),
        "drafts",
        type_="foreignkey",
    )
    op.drop_column("drafts", "revision_feedback")
    op.drop_column("drafts", "vertical_pack_snapshot")
    op.drop_column("drafts", "unsupported_factual_claims")
    op.drop_column("drafts", "internal_link_suggestions")
    op.drop_column("drafts", "citations")
    op.drop_column("drafts", "seo_metadata")
    op.drop_column("drafts", "sections")
    op.drop_column("drafts", "input_fingerprint")
    op.drop_column("drafts", "vertical_pack_version")
    op.drop_column("drafts", "vertical_pack_key")
    op.drop_column("drafts", "content_format")
    op.drop_column("drafts", "revision_of_id")
    op.drop_column("drafts", "research_brief_id")
