from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from editorial_os_api.domain.enums import (
    AssetKind,
    AssetManifestStatus,
    AssetOrigin,
    AssetRightsStatus,
)
from editorial_os_api.vertical_packs import VerticalPack


class CreativeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetVariantSpec(CreativeModel):
    name: str = Field(min_length=1, max_length=120)
    aspect_ratio: str = Field(min_length=3, max_length=30)
    width: int | None = Field(default=None, ge=1, le=20_000)
    height: int | None = Field(default=None, ge=1, le=20_000)


class VisualAssetSpec(CreativeModel):
    slot: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    kind: AssetKind
    purpose: str = Field(min_length=1, max_length=1000)
    prompt: str | None = Field(default=None, max_length=5000)
    alt_text: str | None = Field(default=None, max_length=1000)
    caption: str | None = Field(default=None, max_length=2000)
    filename: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$",
    )
    aspect_ratio: str = Field(min_length=3, max_length=30)
    variants: list[AssetVariantSpec] = Field(default_factory=list)


class VisualBrief(CreativeModel):
    text_only: bool = False
    rationale: str = Field(min_length=1, max_length=3000)
    art_direction: str | None = Field(default=None, max_length=5000)
    assets: list[VisualAssetSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def text_only_and_assets_are_consistent(self) -> VisualBrief:
        if self.text_only and self.assets:
            raise ValueError("text_only visual briefs cannot contain assets.")
        if not self.text_only and not self.assets:
            raise ValueError("non-text-only visual briefs require at least one asset.")
        slots = [asset.slot for asset in self.assets]
        if len(slots) != len(set(slots)):
            raise ValueError("visual asset slots must be unique.")
        return self


class ProviderAsset(CreativeModel):
    origin: AssetOrigin
    uri: str | None = None
    external_id: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=120)
    aspect_ratio: str | None = Field(default=None, max_length=30)
    width: int | None = Field(default=None, ge=1, le=20_000)
    height: int | None = Field(default=None, ge=1, le=20_000)
    source_url: str | None = None
    license_name: str | None = Field(default=None, max_length=255)
    license_url: str | None = None
    rights_status: AssetRightsStatus
    generation_metadata: dict[str, object] = Field(default_factory=dict)
    variants: list[dict[str, object]] = Field(default_factory=list)
    provenance: dict[str, object] = Field(default_factory=dict)


class ApprovalDraftRef(CreativeModel):
    id: UUID
    version: int


class ApprovalManifestRef(CreativeModel):
    id: UUID
    version: int
    status: AssetManifestStatus
    rights_status: AssetRightsStatus
    text_only: bool


class ApprovalAssetRef(CreativeModel):
    id: UUID
    version: int
    slot: str
    kind: AssetKind
    origin: AssetOrigin
    rights_status: AssetRightsStatus
    filename: str | None = None


class GateBApprovalSnapshot(CreativeModel):
    draft: ApprovalDraftRef
    asset_manifest: ApprovalManifestRef
    assets: list[ApprovalAssetRef] = Field(default_factory=list)


class CreativeAgentResult(CreativeModel):
    workflow_run_id: UUID
    draft_id: UUID
    draft_version: int
    manifest_id: UUID
    manifest_version: int
    status: AssetManifestStatus
    text_only: bool
    rights_status: AssetRightsStatus
    asset_ids: list[UUID]
    approval_snapshot: GateBApprovalSnapshot
    workflow_status: str


class CreativePlanner(Protocol):
    name: str

    def plan(
        self,
        workflow_run_id: UUID,
        *,
        draft_title: str,
        draft_deck: str | None,
        draft_body: str,
        locale: str,
        content_format: str,
        vertical_pack: VerticalPack,
        call_key: str,
    ) -> VisualBrief: ...


class AssetProvider(Protocol):
    name: str

    def materialize(
        self,
        workflow_run_id: UUID,
        *,
        draft_id: UUID,
        manifest_input_fingerprint: str,
        spec: VisualAssetSpec,
        vertical_pack: VerticalPack,
        idempotency_key: str,
    ) -> ProviderAsset: ...
