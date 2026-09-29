"""Add Creative Agent asset manifests and provenance metadata.

Revision ID: 20260930_0009
Revises: 20260929_0008
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260930_0009"
down_revision: str | Sequence[str] | None = "20260929_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_manifests",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("text_only", sa.Boolean(), nullable=False),
        sa.Column("rights_status", sa.String(length=30), nullable=False),
        sa.Column("provider_name", sa.String(length=120)),
        sa.Column("provider_request_count", sa.Integer(), nullable=False),
        sa.Column(
            "visual_brief",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "asset_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "approval_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "vertical_pack_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["drafts.id"],
            name=op.f("fk_asset_manifests_draft_id_drafts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_asset_manifests_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_manifests")),
        sa.UniqueConstraint(
            "workflow_run_id",
            "draft_id",
            "input_fingerprint",
            name="workflow_draft_asset_manifest_input",
        ),
        sa.UniqueConstraint(
            "workflow_run_id",
            "draft_id",
            "version",
            name="workflow_draft_asset_manifest_version",
        ),
    )
    op.create_index(
        op.f("ix_asset_manifests_workflow_run_id"),
        "asset_manifests",
        ["workflow_run_id"],
    )
    op.create_index(
        op.f("ix_asset_manifests_draft_id"),
        "asset_manifests",
        ["draft_id"],
    )

    op.drop_constraint(
        "workflow_asset_version_kind",
        "assets",
        type_="unique",
    )
    op.add_column("assets", sa.Column("manifest_id", sa.Uuid()))
    op.add_column("assets", sa.Column("slot", sa.String(length=120)))
    op.add_column(
        "assets",
        sa.Column(
            "origin",
            sa.String(length=30),
            server_default="PROVIDED",
            nullable=False,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "provider",
            sa.String(length=120),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column("assets", sa.Column("external_id", sa.String(length=255)))
    op.add_column("assets", sa.Column("filename", sa.String(length=255)))
    op.add_column("assets", sa.Column("mime_type", sa.String(length=120)))
    op.add_column("assets", sa.Column("aspect_ratio", sa.String(length=30)))
    op.add_column("assets", sa.Column("width", sa.Integer()))
    op.add_column("assets", sa.Column("height", sa.Integer()))
    op.add_column("assets", sa.Column("source_url", sa.Text()))
    op.add_column("assets", sa.Column("license_name", sa.String(length=255)))
    op.add_column("assets", sa.Column("license_url", sa.Text()))
    op.add_column(
        "assets",
        sa.Column(
            "rights_status",
            sa.String(length=30),
            server_default="REVIEW_REQUIRED",
            nullable=False,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "generation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "variants",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE assets
        SET slot = 'legacy:' || id::text
        WHERE slot IS NULL
        """
    )
    op.alter_column("assets", "slot", nullable=False)
    op.create_foreign_key(
        op.f("fk_assets_manifest_id_asset_manifests"),
        "assets",
        "asset_manifests",
        ["manifest_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_assets_manifest_id"),
        "assets",
        ["manifest_id"],
    )
    op.create_unique_constraint(
        "asset_manifest_slot_version",
        "assets",
        ["manifest_id", "slot", "version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "asset_manifest_slot_version",
        "assets",
        type_="unique",
    )
    op.drop_index(op.f("ix_assets_manifest_id"), table_name="assets")
    op.drop_constraint(
        op.f("fk_assets_manifest_id_asset_manifests"),
        "assets",
        type_="foreignkey",
    )
    op.drop_column("assets", "variants")
    op.drop_column("assets", "generation_metadata")
    op.drop_column("assets", "rights_status")
    op.drop_column("assets", "license_url")
    op.drop_column("assets", "license_name")
    op.drop_column("assets", "source_url")
    op.drop_column("assets", "height")
    op.drop_column("assets", "width")
    op.drop_column("assets", "aspect_ratio")
    op.drop_column("assets", "mime_type")
    op.drop_column("assets", "filename")
    op.drop_column("assets", "external_id")
    op.drop_column("assets", "provider")
    op.drop_column("assets", "origin")
    op.drop_column("assets", "slot")
    op.drop_column("assets", "manifest_id")
    op.create_unique_constraint(
        "workflow_asset_version_kind",
        "assets",
        ["workflow_run_id", "version", "kind"],
    )

    op.drop_index(
        op.f("ix_asset_manifests_draft_id"),
        table_name="asset_manifests",
    )
    op.drop_index(
        op.f("ix_asset_manifests_workflow_run_id"),
        table_name="asset_manifests",
    )
    op.drop_table("asset_manifests")
