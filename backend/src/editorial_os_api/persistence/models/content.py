from uuid import UUID

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from editorial_os_api.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


draft_claim_links = Table(
    "draft_claim_links",
    Base.metadata,
    Column(
        "draft_id",
        Uuid(as_uuid=True),
        ForeignKey("drafts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "claim_id",
        Uuid(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("support_status", String(20), nullable=False),
)


class Draft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "drafts"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "locale", "version", name="workflow_draft_version"),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    editorial_brief_id: Mapped[UUID] = mapped_column(
        ForeignKey("editorial_briefs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    locale: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    deck: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "version", "kind", name="workflow_asset_version_kind"),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    uri: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    owner_key: Mapped[str] = mapped_column(String(255), nullable=False)
