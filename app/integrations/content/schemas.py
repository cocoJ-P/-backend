"""Content ingestion enums and pipeline schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.time import to_iso8601
from app.domains.opportunity.schemas import OpportunitySourceResponse


class InputType(StrEnum):
    URL = "url"
    TEXT = "text"


class FetchStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    INVALID_URL = "invalid_url"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"


class ExtractionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_REQUIRED = "not_required"
    INSUFFICIENT_CONTENT = "insufficient_content"
    UNSUPPORTED = "unsupported"


class NormalizedContent(BaseModel):
    input_type: InputType
    original_input: str
    source_url: str | None = None
    resolved_url: str | None = None
    content_type: str | None = None
    title: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    text: str | None = None
    excerpt: str | None = None
    fetch_status: FetchStatus
    extraction_status: ExtractionStatus
    http_status: int | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_serializer("published_at")
    def serialize_published_at(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class IngestRequest(BaseModel):
    content_type: InputType
    content: str


class FetchResult(BaseModel):
    source_url: str
    resolved_url: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    body: bytes = b""
    fetch_status: FetchStatus
    error_code: str | None = None
    error_message: str | None = None


class ExtractedDocument(BaseModel):
    title: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    text: str | None = None
    extraction_status: ExtractionStatus
    warnings: list[str] = Field(default_factory=list)


class IngestedContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    input_type: InputType
    source_url: str | None
    resolved_url: str | None
    content_type: str | None
    raw_title: str | None
    raw_publisher: str | None
    raw_published_at: datetime | None
    normalized_text: str | None
    fetch_status: FetchStatus
    extraction_status: ExtractionStatus
    http_status: int | None
    warnings: list[str] | None
    created_at: datetime

    @field_serializer("raw_published_at", "created_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class IngestResponse(BaseModel):
    normalized_content: NormalizedContent
    source: OpportunitySourceResponse
    ingestion: IngestedContentResponse
