from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from editorial_os_api.domain.enums import (
    ClaimSupportStatus,
    ConfidenceClass,
    RiskClass,
)
from editorial_os_api.vertical_packs import VerticalPack


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentEvidenceReference(ContentModel):
    evidence_id: UUID
    url: str
    tier: str
    stance: str


class ContentClaimContext(ContentModel):
    claim_id: UUID
    claim_key: str
    statement: str
    material: bool
    confidence_class: ConfidenceClass
    risk_class: RiskClass
    support_status: ClaimSupportStatus
    contested: bool = False
    stale: bool = False
    evidence: list[ContentEvidenceReference] = Field(default_factory=list)


class DraftFactualAssertion(ContentModel):
    statement: str = Field(min_length=1, max_length=2000)
    claim_key: str | None = Field(default=None, max_length=128)


class DraftSectionOutput(ContentModel):
    heading: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1)
    factual_assertions: list[DraftFactualAssertion] = Field(default_factory=list)


class SeoMetadataOutput(ContentModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    keywords: list[str] = Field(default_factory=list)
    slug: str | None = Field(default=None, max_length=240)


class InternalLinkSuggestion(ContentModel):
    anchor_text: str = Field(min_length=1, max_length=200)
    target_query: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)


class ContentDraftOutput(ContentModel):
    headline: str = Field(min_length=1, max_length=300)
    deck: str | None = Field(default=None, max_length=600)
    sections: list[DraftSectionOutput] = Field(min_length=1)
    seo: SeoMetadataOutput
    internal_links: list[InternalLinkSuggestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def body_must_not_be_empty(self) -> ContentDraftOutput:
        if not any(section.body.strip() for section in self.sections):
            raise ValueError("At least one non-empty draft section is required.")
        return self


class ContentAgentResult(ContentModel):
    workflow_run_id: UUID
    draft_id: UUID
    version: int
    locale: str
    content_format: str
    vertical_pack_key: str
    vertical_pack_version: str
    claim_ids: list[UUID]
    unsupported_factual_claims: list[str]
    citation_count: int
    revision_of_id: UUID | None = None
    workflow_status: str


class ContentAdapter(Protocol):
    name: str

    def generate(
        self,
        workflow_run_id: UUID,
        *,
        claims: list[ContentClaimContext],
        vertical_pack: VerticalPack,
        locale: str,
        content_format: str,
        angle: str,
        call_key: str,
    ) -> ContentDraftOutput: ...

    def revise(
        self,
        workflow_run_id: UUID,
        *,
        previous: ContentDraftOutput,
        feedback: str,
        claims: list[ContentClaimContext],
        vertical_pack: VerticalPack,
        locale: str,
        content_format: str,
        angle: str,
        call_key: str,
    ) -> ContentDraftOutput: ...
