"""Create canonical editorial domain and audit ledger.

Revision ID: 20260928_0002
Revises: 20260928_0001
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260928_0002"
down_revision: str | Sequence[str] | None = "20260928_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("default_evidence_tier", sa.String(length=2), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("redact_raw_content", sa.Boolean(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
    )

    op.create_table(
        "workflow_runs",
        sa.Column("vertical_key", sa.String(length=120), nullable=False),
        sa.Column("vertical_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("risk_class", sa.String(length=2), nullable=False),
        sa.Column("confidence_class", sa.String(length=2), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
        sa.UniqueConstraint("idempotency_key", name="workflow_idempotency"),
    )
    op.create_index(op.f("ix_workflow_runs_status"), "workflow_runs", ["status"])
    op.create_index(op.f("ix_workflow_runs_vertical_key"), "workflow_runs", ["vertical_key"])

    op.create_table(
        "source_items",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=500), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("extracted_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_source_items_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_items")),
        sa.UniqueConstraint("source_id", "external_id", name="source_external_id"),
        sa.UniqueConstraint("source_id", "content_hash", name="source_content_hash"),
    )
    op.create_index(op.f("ix_source_items_source_id"), "source_items", ["source_id"])

    op.create_table(
        "topic_candidates",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("proposed_angle", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("risk_class", sa.String(length=2), nullable=False),
        sa.Column("confidence_class", sa.String(length=2), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_topic_candidates_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic_candidates")),
    )
    op.create_index(
        op.f("ix_topic_candidates_workflow_run_id"),
        "topic_candidates",
        ["workflow_run_id"],
    )

    op.create_table(
        "editorial_briefs",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("angle", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("instructions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_editorial_briefs_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_editorial_briefs")),
        sa.UniqueConstraint("workflow_run_id", "version", name="workflow_brief_version"),
    )
    op.create_index(
        op.f("ix_editorial_briefs_workflow_run_id"),
        "editorial_briefs",
        ["workflow_run_id"],
    )

    op.create_table(
        "evidence_items",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_item_id", sa.Uuid(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("tier", sa.String(length=2), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_item_id"],
            ["source_items.id"],
            name=op.f("fk_evidence_items_source_item_id_source_items"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_evidence_items_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_items")),
    )
    op.create_index(
        op.f("ix_evidence_items_source_item_id"),
        "evidence_items",
        ["source_item_id"],
    )
    op.create_index(
        op.f("ix_evidence_items_workflow_run_id"),
        "evidence_items",
        ["workflow_run_id"],
    )

    op.create_table(
        "claims",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("material", sa.Boolean(), nullable=False),
        sa.Column("confidence_class", sa.String(length=2), nullable=False),
        sa.Column("risk_class", sa.String(length=2), nullable=False),
        sa.Column("contested", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_claims_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claims")),
    )
    op.create_index(op.f("ix_claims_workflow_run_id"), "claims", ["workflow_run_id"])

    op.create_table(
        "claim_evidence_links",
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            name=op.f("fk_claim_evidence_links_claim_id_claims"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_item_id"],
            ["evidence_items.id"],
            name=op.f("fk_claim_evidence_links_evidence_item_id_evidence_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "claim_id",
            "evidence_item_id",
            name=op.f("pk_claim_evidence_links"),
        ),
    )

    op.create_table(
        "drafts",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("editorial_brief_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("deck", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("metadata_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["editorial_brief_id"],
            ["editorial_briefs.id"],
            name=op.f("fk_drafts_editorial_brief_id_editorial_briefs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_drafts_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drafts")),
        sa.UniqueConstraint(
            "workflow_run_id",
            "locale",
            "version",
            name="workflow_draft_version",
        ),
    )
    op.create_index(op.f("ix_drafts_workflow_run_id"), "drafts", ["workflow_run_id"])

    op.create_table(
        "assets",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("owner_key", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_assets_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
        sa.UniqueConstraint(
            "workflow_run_id",
            "version",
            "kind",
            name="workflow_asset_version_kind",
        ),
    )
    op.create_index(op.f("ix_assets_workflow_run_id"), "assets", ["workflow_run_id"])

    op.create_table(
        "gate_decisions",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("gate", sa.String(length=1), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("artifact_type", sa.String(length=80), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_version", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_gate_decisions_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gate_decisions")),
        sa.UniqueConstraint(
            "workflow_run_id",
            "gate",
            "artifact_type",
            "artifact_id",
            "artifact_version",
            "outcome",
            "decided_at",
            name="gate_decision_event",
        ),
    )
    op.create_index(
        op.f("ix_gate_decisions_workflow_run_id"),
        "gate_decisions",
        ["workflow_run_id"],
    )

    op.create_table(
        "audit_events",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
        sa.Column("actor_kind", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_audit_events_workflow_run_id_workflow_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_event_type"),
        "audit_events",
        ["event_type"],
    )
    op.create_index(
        op.f("ix_audit_events_occurred_at"),
        "audit_events",
        ["occurred_at"],
    )
    op.create_index(
        op.f("ix_audit_events_workflow_run_id"),
        "audit_events",
        ["workflow_run_id"],
    )

    op.create_table(
        "publications",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("owner_key", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=500), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipt", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["drafts.id"],
            name=op.f("fk_publications_draft_id_drafts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_publications_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publications")),
        sa.UniqueConstraint(
            "provider",
            "target",
            "idempotency_key",
            name="publication_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_publications_workflow_run_id"),
        "publications",
        ["workflow_run_id"],
    )

    op.create_table(
        "distribution_jobs",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("publication_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("channel", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("owner_key", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=500), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("receipt", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["publication_id"],
            ["publications.id"],
            name=op.f("fk_distribution_jobs_publication_id_publications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_distribution_jobs_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_distribution_jobs")),
        sa.UniqueConstraint(
            "provider",
            "channel",
            "idempotency_key",
            name="distribution_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_distribution_jobs_publication_id"),
        "distribution_jobs",
        ["publication_id"],
    )
    op.create_index(
        op.f("ix_distribution_jobs_workflow_run_id"),
        "distribution_jobs",
        ["workflow_run_id"],
    )

    op.create_table(
        "performance_snapshots",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("publication_id", sa.Uuid(), nullable=True),
        sa.Column("distribution_job_id", sa.Uuid(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["distribution_job_id"],
            ["distribution_jobs.id"],
            name=op.f(
                "fk_performance_snapshots_distribution_job_id_distribution_jobs"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["publication_id"],
            ["publications.id"],
            name=op.f("fk_performance_snapshots_publication_id_publications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_performance_snapshots_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_performance_snapshots")),
    )
    op.create_index(
        op.f("ix_performance_snapshots_distribution_job_id"),
        "performance_snapshots",
        ["distribution_job_id"],
    )
    op.create_index(
        op.f("ix_performance_snapshots_publication_id"),
        "performance_snapshots",
        ["publication_id"],
    )
    op.create_index(
        op.f("ix_performance_snapshots_workflow_run_id"),
        "performance_snapshots",
        ["workflow_run_id"],
    )

    op.execute(
        """
        CREATE FUNCTION editorial_os_reject_append_only_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER gate_decisions_append_only
        BEFORE UPDATE OR DELETE ON gate_decisions
        FOR EACH ROW EXECUTE FUNCTION editorial_os_reject_append_only_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION editorial_os_reject_append_only_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS gate_decisions_append_only ON gate_decisions")
    op.execute("DROP FUNCTION IF EXISTS editorial_os_reject_append_only_mutation()")

    op.drop_index(
        op.f("ix_performance_snapshots_workflow_run_id"),
        table_name="performance_snapshots",
    )
    op.drop_index(
        op.f("ix_performance_snapshots_publication_id"),
        table_name="performance_snapshots",
    )
    op.drop_index(
        op.f("ix_performance_snapshots_distribution_job_id"),
        table_name="performance_snapshots",
    )
    op.drop_table("performance_snapshots")

    op.drop_index(
        op.f("ix_distribution_jobs_workflow_run_id"),
        table_name="distribution_jobs",
    )
    op.drop_index(
        op.f("ix_distribution_jobs_publication_id"),
        table_name="distribution_jobs",
    )
    op.drop_table("distribution_jobs")

    op.drop_index(
        op.f("ix_publications_workflow_run_id"),
        table_name="publications",
    )
    op.drop_table("publications")

    op.drop_index(
        op.f("ix_audit_events_workflow_run_id"),
        table_name="audit_events",
    )
    op.drop_index(op.f("ix_audit_events_occurred_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index(
        op.f("ix_gate_decisions_workflow_run_id"),
        table_name="gate_decisions",
    )
    op.drop_table("gate_decisions")

    op.drop_index(op.f("ix_assets_workflow_run_id"), table_name="assets")
    op.drop_table("assets")

    op.drop_index(op.f("ix_drafts_workflow_run_id"), table_name="drafts")
    op.drop_table("drafts")

    op.drop_table("claim_evidence_links")

    op.drop_index(op.f("ix_claims_workflow_run_id"), table_name="claims")
    op.drop_table("claims")

    op.drop_index(
        op.f("ix_evidence_items_workflow_run_id"),
        table_name="evidence_items",
    )
    op.drop_index(
        op.f("ix_evidence_items_source_item_id"),
        table_name="evidence_items",
    )
    op.drop_table("evidence_items")

    op.drop_index(
        op.f("ix_editorial_briefs_workflow_run_id"),
        table_name="editorial_briefs",
    )
    op.drop_table("editorial_briefs")

    op.drop_index(
        op.f("ix_topic_candidates_workflow_run_id"),
        table_name="topic_candidates",
    )
    op.drop_table("topic_candidates")

    op.drop_index(op.f("ix_source_items_source_id"), table_name="source_items")
    op.drop_table("source_items")

    op.drop_index(op.f("ix_workflow_runs_vertical_key"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_status"), table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_table("sources")
