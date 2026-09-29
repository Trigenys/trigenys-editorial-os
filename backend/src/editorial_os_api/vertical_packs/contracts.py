from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VerticalPackModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VoiceRules(VerticalPackModel):
    tone: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)
    prohibited_phrases: list[str] = Field(default_factory=list)
    max_headline_chars: int = Field(default=120, ge=20, le=300)
    max_deck_chars: int = Field(default=240, ge=20, le=600)
    min_sections: int = Field(default=1, ge=1, le=20)


class SourceRules(VerticalPackModel):
    require_citations_for_material_claims: bool = True
    allow_reviewed_contested_claims: bool = True
    include_source_urls_in_prompt: bool = True


class SeoRules(VerticalPackModel):
    title_max_chars: int = Field(default=60, ge=20, le=120)
    description_max_chars: int = Field(default=160, ge=60, le=320)
    require_keywords: bool = True


class VerticalPack(VerticalPackModel):
    key: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    version: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)
    audience: str = Field(min_length=1, max_length=1000)
    locales: list[str] = Field(min_length=1)
    default_locale: str = Field(min_length=2, max_length=20)
    formats: list[str] = Field(min_length=1)
    default_format: str = Field(min_length=1, max_length=80)
    voice: VoiceRules = Field(default_factory=VoiceRules)
    source_rules: SourceRules = Field(default_factory=SourceRules)
    seo: SeoRules = Field(default_factory=SeoRules)
    internal_link_topics: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def defaults_must_be_supported(self) -> VerticalPack:
        if len(self.locales) != len(set(self.locales)):
            raise ValueError("locales must be unique.")
        if len(self.formats) != len(set(self.formats)):
            raise ValueError("formats must be unique.")
        if self.default_locale not in self.locales:
            raise ValueError("default_locale must be listed in locales.")
        if self.default_format not in self.formats:
            raise ValueError("default_format must be listed in formats.")
        return self

    def supports(self, *, locale: str, content_format: str) -> bool:
        return locale in self.locales and content_format in self.formats
