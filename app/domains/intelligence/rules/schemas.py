"""Rule Layer output schemas. These are signals, not final IntelligenceResult."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.core.time import to_iso8601
from app.domains.intelligence.enums import (
    AmountKind,
    DateCandidateKind,
    SignalCategory,
    SignalStrength,
    URLCandidateKind,
)
from app.domains.intelligence.schemas import IntelligenceEvidence

RULE_VERSION = "rules-v1"
MAX_EVIDENCE_PER_SIGNAL = 5


class RuleSignal(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    category: SignalCategory
    strength: SignalStrength
    description: str
    occurrence_count: int = Field(default=1, ge=1)
    evidence_ids: list[str] = Field(default_factory=list)


class DateCandidate(BaseModel):
    value: date | None = None
    kind: DateCandidateKind
    raw_text: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_id: str = Field(min_length=1, max_length=64)


class URLCandidate(BaseModel):
    url: str = Field(min_length=1, max_length=1024)
    kind: URLCandidateKind
    source: str = Field(min_length=1, max_length=64)
    evidence_id: str = Field(min_length=1, max_length=64)


class AmountCandidate(BaseModel):
    raw_text: str = Field(min_length=1, max_length=300)
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = None
    unit: str | None = None
    kind: AmountKind
    evidence_id: str = Field(min_length=1, max_length=64)


class EntityCandidate(BaseModel):
    text: str = Field(min_length=1, max_length=255)
    kind: str = "organization"
    evidence_id: str = Field(min_length=1, max_length=64)


class RuleAnalysisMetadata(BaseModel):
    rule_version: str = RULE_VERSION
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return to_iso8601(value)


class RuleAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: list[RuleSignal] = Field(default_factory=list)
    date_candidates: list[DateCandidate] = Field(default_factory=list)
    url_candidates: list[URLCandidate] = Field(default_factory=list)
    amount_candidates: list[AmountCandidate] = Field(default_factory=list)
    entity_candidates: list[EntityCandidate] = Field(default_factory=list)
    evidence: list[IntelligenceEvidence] = Field(default_factory=list)
    metadata: RuleAnalysisMetadata

    @model_validator(mode="after")
    def evidence_ids_must_exist(self) -> "RuleAnalysisResult":
        known = {item.id for item in self.evidence}
        referenced: list[str] = []
        for signal in self.signals:
            referenced.extend(signal.evidence_ids)
        for candidate in (
            *self.date_candidates,
            *self.url_candidates,
            *self.amount_candidates,
            *self.entity_candidates,
        ):
            referenced.append(candidate.evidence_id)
        missing = [item for item in referenced if item not in known]
        if missing:
            raise ValueError(f"unknown evidence_ids: {missing}")
        return self
