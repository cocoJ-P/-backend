"""HTTP schemas for Opportunity Intelligence. Claims, not verified facts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer

from app.core.time import to_iso8601
from app.domains.intelligence.enums import IntelligenceRunStatus
from app.domains.intelligence.schemas import ContentIntelligenceResult


class AnalyzeRequest(BaseModel):
    ingestion_id: UUID | None = None
    force: bool = False


class IntelligenceRunResponse(BaseModel):
    """Run metadata. status=succeeded means analysis finished, not verification."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    ingestion_id: UUID
    status: IntelligenceRunStatus
    input_hash: str
    analysis_fingerprint: str
    rule_version: str
    prompt_version: str
    provider: str
    model: str
    input_char_count: int
    input_truncated: bool
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime

    @field_serializer("started_at", "completed_at", "created_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class IntelligenceAnalyzeResponse(BaseModel):
    run: IntelligenceRunResponse
    reused: bool
    intelligence_result: ContentIntelligenceResult | None = None


class IntelligenceRunDetailResponse(BaseModel):
    run: IntelligenceRunResponse
    intelligence_result: ContentIntelligenceResult | None = None


class IntelligenceAnalysisExecution(BaseModel):
    run: IntelligenceRunResponse
    intelligence_result: ContentIntelligenceResult | None = None
    reused: bool
