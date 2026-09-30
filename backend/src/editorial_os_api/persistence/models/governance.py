from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from editorial_os_api.persistence.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utcnow,
)


class GateDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "gate_decisions"
    __table_args__ = (
        UniqueConstraint(
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

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gate: Mapped[str] = mapped_column(String(1), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(nullable=False)
    artifact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class EditorialQAReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "editorial_qa_reviews"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "draft_id",
            "manifest_id",
            "input_fingerprint",
            name="workflow_qa_input_fingerprint",
        ),
        UniqueConstraint(
            "workflow_run_id",
            "version",
            name="workflow_qa_review_version",
        ),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    draft_id: Mapped[UUID] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manifest_id: Mapped[UUID] = mapped_column(
        ForeignKey("asset_manifests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_class: Mapped[str] = mapped_column(String(2), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(2), nullable=False)
    human_approval_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    gate_b_ready: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    adapter_name: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    findings: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    reason_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    subject_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    workflow_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        index=True,
    )
    actor_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
        index=True,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
