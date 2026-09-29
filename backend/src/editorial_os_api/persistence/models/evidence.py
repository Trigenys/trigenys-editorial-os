from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from editorial_os_api.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

claim_evidence_links = Table(
    "claim_evidence_links",
    Base.metadata,
    Column(
        "claim_id",
        Uuid(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "evidence_item_id",
        Uuid(as_uuid=True),
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "stance",
        String(20),
        default="SUPPORTS",
        server_default="SUPPORTS",
        nullable=False,
    ),
    Column("reason_code", String(120)),
)


class EvidenceItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_items"

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_items.id", ondelete="SET NULL"),
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(String(2), nullable=False)
    source_role: Mapped[str] = mapped_column(
        String(20),
        default="SECONDARY",
        server_default="SECONDARY",
        nullable=False,
    )
    stale: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    extraction_method: Mapped[str] = mapped_column(
        String(80),
        default="legacy",
        server_default="legacy",
        nullable=False,
    )
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retain_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "claim_key", name="workflow_claim_key"),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_key: Mapped[str] = mapped_column(String(128), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    material: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confidence_class: Mapped[str] = mapped_column(String(2), nullable=False)
    confidence_reason_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default="[]",
        nullable=False,
    )
    risk_class: Mapped[str] = mapped_column(String(2), nullable=False)
    support_status: Mapped[str] = mapped_column(
        String(20),
        default="UNKNOWN",
        server_default="UNKNOWN",
        nullable=False,
    )
    stale: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    contested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ResearchBrief(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_briefs"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "version",
            name="workflow_research_brief_version",
        ),
        UniqueConstraint(
            "workflow_run_id",
            "input_fingerprint",
            name="workflow_research_input_fingerprint",
        ),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("topic_candidates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence_class: Mapped[str] = mapped_column(String(2), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(2), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    contradiction_claim_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    unsupported_claim_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    stale_claim_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    source_plan: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    budget_usage: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_resolved_by: Mapped[str | None] = mapped_column(String(255))
    review_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
