"""Expand source registry and separate raw fetches.

Revision ID: 20260928_0005
Revises: 20260928_0004
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260928_0005"
down_revision: str | Sequence[str] | None = "20260928_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("trust_tier", sa.String(length=2), server_default="E1", nullable=False),
    )
    op.add_column("sources", sa.Column("locale", sa.String(length=32), nullable=True))
    op.add_column(
        "sources",
        sa.Column(
            "vertical_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "fetch_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "health_status",
            sa.String(length=30),
            server_default="HEALTHY",
            nullable=False,
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column("sources", sa.Column("next_fetch_at", sa.DateTime(timezone=True)))
    op.add_column("sources", sa.Column("last_success_at", sa.DateTime(timezone=True)))
    op.add_column("sources", sa.Column("last_failure_at", sa.DateTime(timezone=True)))
    op.add_column("sources", sa.Column("last_error_kind", sa.String(length=80)))
    op.add_column("sources", sa.Column("cursor", sa.Text()))

    op.create_table(
        "source_fetches",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("adapter", sa.String(length=80), nullable=False),
        sa.Column("requested_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("failure_kind", sa.String(length=80)),
        sa.Column("retryable", sa.Boolean()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("content_type", sa.String(length=200)),
        sa.Column("raw_payload", sa.Text()),
        sa.Column("raw_sha256", sa.String(length=64)),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_source_fetches_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_fetches")),
    )
    op.create_index(
        op.f("ix_source_fetches_source_id"),
        "source_fetches",
        ["source_id"],
    )

    op.add_column("source_items", sa.Column("source_fetch_id", sa.Uuid()))
    op.add_column("source_items", sa.Column("identity_key", sa.String(length=128)))
    op.add_column("source_items", sa.Column("locale", sa.String(length=32)))
    op.add_column(
        "source_items",
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.execute(
        """
        UPDATE source_items
        SET identity_key = encode(
            digest(
                source_id::text || ':' ||
                COALESCE(NULLIF(external_id, ''), canonical_url, id::text),
                'sha256'
            ),
            'hex'
        )
        """
    )
    op.alter_column("source_items", "identity_key", nullable=False)
    op.create_foreign_key(
        op.f("fk_source_items_source_fetch_id_source_fetches"),
        "source_items",
        "source_fetches",
        ["source_fetch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_source_items_source_fetch_id"),
        "source_items",
        ["source_fetch_id"],
    )
    op.create_unique_constraint(
        "source_identity_key",
        "source_items",
        ["source_id", "identity_key"],
    )


def downgrade() -> None:
    op.drop_constraint("source_identity_key", "source_items", type_="unique")
    op.drop_index(op.f("ix_source_items_source_fetch_id"), table_name="source_items")
    op.drop_constraint(
        op.f("fk_source_items_source_fetch_id_source_fetches"),
        "source_items",
        type_="foreignkey",
    )
    op.drop_column("source_items", "provenance")
    op.drop_column("source_items", "locale")
    op.drop_column("source_items", "identity_key")
    op.drop_column("source_items", "source_fetch_id")

    op.drop_index(op.f("ix_source_fetches_source_id"), table_name="source_fetches")
    op.drop_table("source_fetches")

    op.drop_column("sources", "cursor")
    op.drop_column("sources", "last_error_kind")
    op.drop_column("sources", "last_failure_at")
    op.drop_column("sources", "last_success_at")
    op.drop_column("sources", "next_fetch_at")
    op.drop_column("sources", "consecutive_failures")
    op.drop_column("sources", "health_status")
    op.drop_column("sources", "fetch_policy")
    op.drop_column("sources", "vertical_keys")
    op.drop_column("sources", "locale")
    op.drop_column("sources", "trust_tier")
