from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from editorial_os_api.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trust_tier: Mapped[str] = mapped_column(String(2), default="E1", nullable=False)
    default_evidence_tier: Mapped[str] = mapped_column(String(2), default="E1", nullable=False)
    locale: Mapped[str | None] = mapped_column(String(32))
    vertical_keys: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    fetch_policy: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    redact_raw_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    health_status: Mapped[str] = mapped_column(String(30), default="HEALTHY", nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_kind: Mapped[str | None] = mapped_column(String(80))
    cursor: Mapped[str | None] = mapped_column(Text)


class SourceFetch(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "source_fetches"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    adapter: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    failure_kind: Mapped[str | None] = mapped_column(String(80))
    retryable: Mapped[bool | None] = mapped_column(Boolean)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(200))
    raw_payload: Mapped[str | None] = mapped_column(Text)
    raw_sha256: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text)


class SourceItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="source_external_id"),
        UniqueConstraint("source_id", "content_hash", name="source_content_hash"),
        UniqueConstraint("source_id", "identity_key", name="source_identity_key"),
    )

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_fetch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_fetches.id", ondelete="SET NULL"),
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(500))
    identity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    locale: Mapped[str | None] = mapped_column(String(32))
    raw_content: Mapped[str | None] = mapped_column(Text)
    extracted_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    provenance: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retain_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
