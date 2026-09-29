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
        UniqueConstraint(
            "workflow_run_id",
            "locale",
            "version",
            name="workflow_draft_version",
        ),
        UniqueConstraint(
            "workflow_run_id",
            "locale",
            "input_fingerprint",
            name="workflow_draft_input_fingerprint",
        ),
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
    research_brief_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_briefs.id", ondelete="RESTRICT"),
        index=True,
    )
    revision_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("drafts.id", ondelete="SET NULL"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    locale: Mapped[str] = mapped_column(String(20), nullable=False)
    content_format: Mapped[str] = mapped_column(
        String(80),
        default="article",
        server_default="article",
        nullable=False,
    )
    vertical_pack_key: Mapped[str] = mapped_column(
        String(120),
        default="legacy",
        server_default="legacy",
        nullable=False,
    )
    vertical_pack_version: Mapped[str] = mapped_column(
        String(80),
        default="legacy",
        server_default="legacy",
        nullable=False,
    )
    input_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    deck: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    seo_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    citations: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    internal_link_suggestions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    unsupported_factual_claims: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    vertical_pack_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    revision_feedback: Mapped[str | None] = mapped_column(Text)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "version",
            "kind",
            name="workflow_asset_version_kind",
        ),
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
    provenance: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    owner_key: Mapped[str] = mapped_column(String(255), nullable=False)
