from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from editorial_os_api.persistence.base import Base, UUIDPrimaryKeyMixin, utcnow


class ModelUsageRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "model_usage_records"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "call_key", name="model_usage_call_idempotency"),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    task: Mapped[str] = mapped_column(String(80), nullable=False)
    call_key: Mapped[str] = mapped_column(String(255), nullable=False)
    route_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    reserved_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    actual_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    cost_is_estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_kind: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
