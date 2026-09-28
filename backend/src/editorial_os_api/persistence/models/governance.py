from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from editorial_os_api.persistence.base import Base, UUIDPrimaryKeyMixin, utcnow


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
