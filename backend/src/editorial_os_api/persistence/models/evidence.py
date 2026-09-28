from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Text, Uuid
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
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retain_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claims"

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    material: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confidence_class: Mapped[str] = mapped_column(String(2), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(2), nullable=False)
    contested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
