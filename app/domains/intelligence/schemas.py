"""Opportunity Intelligence Pydantic contracts.

All extracted business fields are claims from the current content. They are
not verified facts, matching scores, or provenance conclusions.

Semantic boundaries:
- publisher is who published this page; claimed_issuer is who the page says
  issued the opportunity.
- source title may be marketing copy; claimed_title should be the opportunity
  name described in the content.
- source published_at is when the page appeared; claimed_publish_date is when
  the opportunity document is said to have been published.
- marketing_level=high does not mean the content is fake.
- intermediary_level=likely does not mean the opportunity is invalid.
- apparent_source_type=official_like is not a verified official source.
- Unknown values stay null / unknown. Do not guess.
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.core.time import to_iso8601
from app.domains.intelligence.contracts import (
    DEFAULT_ANALYZER_VERSION,
    EVIDENCE_TEXT_MAX_CHARS,
    SCHEMA_VERSION,
)
from app.domains.intelligence.enums import (
    ApparentSourceType,
    ClaimedStatus,
    ContentNature,
    EvidenceKind,
    IntermediaryLevel,
    MarketingLevel,
    OpportunityRelevance,
    OriginalityClaim,
)
from app.domains.opportunity.enums import OpportunityType, RequirementOperator


class ContentIntelligenceInput(BaseModel):
    """Normalized content ready for analysis. Empty text is invalid."""

    source_id: UUID
    ingestion_id: UUID
    title: str | None = None
    publisher: str | None = None
    source_url: str | None = Field(default=None, max_length=1024)
    published_at: datetime | None = None
    normalized_text: str = Field(min_length=1)

    @field_validator("normalized_text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("normalized_text must not be blank")
        return value

    @field_serializer("published_at")
    def serialize_published_at(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class IntelligenceAnalysis(BaseModel):
    content_nature: ContentNature
    opportunity_relevance: OpportunityRelevance
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class SourceAssessment(BaseModel):
    apparent_source_type: ApparentSourceType
    marketing_level: MarketingLevel
    marketing_signals: list[str] = Field(default_factory=list)
    intermediary_level: IntermediaryLevel
    intermediary_signals: list[str] = Field(default_factory=list)
    originality_claim: OriginalityClaim


class ClaimedFunding(BaseModel):
    description: str | None = None
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = None
    amount_type: str | None = None


class ClaimedResourceValue(BaseModel):
    funding: ClaimedFunding | None = None
    scenario: bool | str | None = None
    financing: str | None = None
    service: str | None = None
    other: list[str] = Field(default_factory=list)


class ClaimedRequirement(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=255)
    operator: RequirementOperator
    expected_value: Any = None
    required: bool = False
    description: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class OpportunityClaim(BaseModel):
    """Opportunity as claimed by the current content, not a verified Opportunity."""

    claimed_type: OpportunityType | None = None
    claimed_title: str | None = Field(default=None, max_length=512)
    claimed_issuer: str | None = Field(default=None, max_length=255)
    claimed_region: str | None = Field(default=None, max_length=255)
    claimed_publish_date: date | None = None
    claimed_deadline: date | None = None
    claimed_status: ClaimedStatus | None = None
    claimed_summary: str | None = None
    claimed_resource_value: ClaimedResourceValue | None = None
    claimed_requirements: list[ClaimedRequirement] = Field(default_factory=list)
    claimed_required_materials: list[str] = Field(default_factory=list)
    claimed_application_process: list[str] = Field(default_factory=list)
    claimed_official_url: str | None = Field(default=None, max_length=1024)
    claim_confidence: float = Field(ge=0.0, le=1.0)


class IntelligenceEvidence(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    kind: EvidenceKind
    field: str | None = Field(default=None, max_length=128)
    text: str = Field(min_length=1, max_length=EVIDENCE_TEXT_MAX_CHARS)
    source: str | None = Field(default=None, max_length=64)


class IntelligenceMetadata(BaseModel):
    schema_version: str = SCHEMA_VERSION
    analyzer_version: str = DEFAULT_ANALYZER_VERSION
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return to_iso8601(value)


class ContentIntelligenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: IntelligenceAnalysis
    source_assessment: SourceAssessment
    opportunity_claim: OpportunityClaim | None = None
    evidence: list[IntelligenceEvidence] = Field(default_factory=list)
    metadata: IntelligenceMetadata

    @model_validator(mode="after")
    def evidence_ids_must_exist(self) -> "ContentIntelligenceResult":
        known = {item.id for item in self.evidence}
        referenced: list[str] = []
        if self.opportunity_claim is not None:
            for requirement in self.opportunity_claim.claimed_requirements:
                referenced.extend(requirement.evidence_ids)
        missing = [item for item in referenced if item not in known]
        if missing:
            raise ValueError(f"unknown evidence_ids: {missing}")
        return self
