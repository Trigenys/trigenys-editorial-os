from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from editorial_os_api.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Publication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint("provider", "target", "idempotency_key", name="publication_idempotency"),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    draft_id: Mapped[UUID] = mapped_column(
        ForeignKey("drafts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_key: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(500))
    external_url: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class DistributionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "distribution_jobs"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "channel",
            "idempotency_key",
            name="distribution_idempotency",
        ),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    publication_id: Mapped[UUID] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_key: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(500))
    external_url: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    receipt: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class PerformanceSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "performance_snapshots"

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    publication_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("publications.id", ondelete="SET NULL"),
        index=True,
    )
    distribution_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("distribution_jobs.id", ondelete="SET NULL"),
        index=True,
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
