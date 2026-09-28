from uuid import UUID

from sqlalchemy import (
    Column,
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


brief_claim_links = Table(
    "brief_claim_links",
    Base.metadata,
    Column(
        "editorial_brief_id",
        Uuid(as_uuid=True),
        ForeignKey("editorial_briefs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "claim_id",
        Uuid(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="workflow_idempotency"),)

    vertical_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    vertical_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    risk_class: Mapped[str] = mapped_column(String(2), default="R0", nullable=False)
    confidence_class: Mapped[str] = mapped_column(String(2), default="C0", nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    context: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class TopicCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "topic_candidates"

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_angle: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(2), nullable=False)
    confidence_class: Mapped[str] = mapped_column(String(2), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class EditorialBrief(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "editorial_briefs"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "version", name="workflow_brief_version"),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    angle: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(20), nullable=False)
    instructions: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
