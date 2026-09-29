from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from editorial_os_api.domain.enums import TopicDecision, TopicUrgency


class IntelligenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScoreWeights(IntelligenceModel):
    novelty: float = Field(default=0.45, ge=0, le=1)
    relevance: float = Field(default=0.40, ge=0, le=1)
    source_diversity: float = Field(default=0.15, ge=0, le=1)

    @model_validator(mode="after")
    def weights_must_have_mass(self) -> ScoreWeights:
        if self.novelty + self.relevance + self.source_diversity <= 0:
            raise ValueError("At least one scoring weight must be greater than zero.")
        return self


class DecisionThresholds(IntelligenceModel):
    propose_min: int = Field(default=70, ge=0, le=100)
    watch_min: int = Field(default=45, ge=0, le=100)
    stale_after_hours: int = Field(default=72, ge=1, le=24 * 365)
    novelty_window_hours: int = Field(default=24 * 7, ge=1, le=24 * 365)

    @model_validator(mode="after")
    def watch_must_not_exceed_propose(self) -> DecisionThresholds:
        if self.watch_min > self.propose_min:
            raise ValueError("watch_min cannot exceed propose_min.")
        return self


class VerticalIntelligencePolicy(IntelligenceModel):
    vertical_key: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=80)
    eligible_locales: list[str] = Field(default_factory=list)
    priority_terms: list[str] = Field(default_factory=list)
    blocked_terms: list[str] = Field(default_factory=list)
    supported_formats: list[str] = Field(default_factory=lambda: ["article"])
    default_format: str = Field(default="article", min_length=1, max_length=80)
    cluster_similarity_threshold: float = Field(default=0.45, ge=0.05, le=1)
    weights: ScoreWeights = Field(default_factory=ScoreWeights)
    thresholds: DecisionThresholds = Field(default_factory=DecisionThresholds)
    use_model_strategy: bool = True

    @model_validator(mode="after")
    def default_format_must_be_supported(self) -> VerticalIntelligencePolicy:
        if self.default_format not in self.supported_formats:
            raise ValueError("default_format must be listed in supported_formats.")
        return self


class SignalDocument(IntelligenceModel):
    id: UUID
    source_id: UUID
    title: str
    summary: str = ""
    locale: str | None = None
    published_at_iso: str | None = None
    observed_at_iso: str


class ScoreBreakdown(IntelligenceModel):
    novelty: int = Field(ge=0, le=100)
    relevance: int = Field(ge=0, le=100)
    source_diversity: int = Field(ge=0, le=100)
    composite: int = Field(ge=0, le=100)
    stale: bool
    reason_codes: list[str] = Field(default_factory=list)


class EditorialStrategyOutput(IntelligenceModel):
    proposed_angle: str = Field(min_length=1, max_length=1000)
    proposed_format: str = Field(min_length=1, max_length=80)
    urgency: TopicUrgency


class EditorialIntelligenceResult(IntelligenceModel):
    workflow_run_id: UUID
    candidate_id: UUID
    candidate_version: int
    decision: TopicDecision
    cluster_key: str
    source_item_ids: list[UUID]
    novelty_score: int
    relevance_score: int
    source_diversity_score: int
    composite_score: int
    proposed_angle: str
    proposed_format: str
    urgency: TopicUrgency
    reason_codes: list[str]
    pending_gate: Literal["A"] | None = None
