from uuid import UUID, uuid4

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
    input_fingerprint: Mapped[str] = mapped_column(
        String(128),
        default=lambda: f"legacy:{uuid4()}",
        nullable=False,
    )
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


class AssetManifest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_manifests"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "draft_id",
            "input_fingerprint",
            name="workflow_draft_asset_manifest_input",
        ),
        UniqueConstraint(
            "workflow_run_id",
            "draft_id",
            "version",
            name="workflow_draft_asset_manifest_version",
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
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    text_only: Mapped[bool] = mapped_column(default=False, nullable=False)
    rights_status: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(120))
    provider_request_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    visual_brief: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    asset_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    approval_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    vertical_pack_snapshot: Mapped[dict[str, object]] = mapped_column(
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
        UniqueConstraint(
            "manifest_id",
            "slot",
            "version",
            name="asset_manifest_slot_version",
        ),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manifest_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("asset_manifests.id", ondelete="CASCADE"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[str] = mapped_column(
        String(120),
        default=lambda: f"legacy:{uuid4()}",
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    origin: Mapped[str] = mapped_column(
        String(30),
        default="PROVIDED",
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(120),
        default="legacy",
        nullable=False,
    )
    uri: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(255))
    filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    aspect_ratio: Mapped[str | None] = mapped_column(String(30))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    license_name: Mapped[str | None] = mapped_column(String(255))
    license_url: Mapped[str | None] = mapped_column(Text)
    rights_status: Mapped[str] = mapped_column(
        String(30),
        default="REVIEW_REQUIRED",
        nullable=False,
    )
    alt_text: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    generation_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    variants: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    provenance: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    owner_key: Mapped[str] = mapped_column(String(255), nullable=False)
