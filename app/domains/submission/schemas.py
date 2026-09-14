"""HTTP schemas for UserSubmission. Intelligence result reuses B4 contract."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.time import to_iso8601
from app.domains.identity.schemas import MeEnterprise, MeUser
from app.domains.intelligence.schemas import ContentIntelligenceResult
from app.domains.submission.enums import (
    SubmissionFailureStage,
    SubmissionInputType,
    SubmissionOriginType,
    SubmissionStatus,
)
from app.domains.service_case.schemas import LinkedServiceCase


class CreateUserSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_type: SubmissionInputType
    content: str


class UserActor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str


class UserSubmissionCreateResponse(BaseModel):
    id: UUID
    status: SubmissionStatus
    input_type: SubmissionInputType
    input_preview: str
    origin_type: SubmissionOriginType
    origin_discovery_id: UUID | None
    created_at: datetime
    user: UserActor
    enterprise: MeEnterprise

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return to_iso8601(value)


class UserSubmissionSummary(BaseModel):
    id: UUID
    status: SubmissionStatus
    failure_stage: SubmissionFailureStage | None
    input_type: SubmissionInputType
    input_preview: str
    display_title: str
    submitted_by: UserActor
    origin_type: SubmissionOriginType
    origin_discovery_id: UUID | None
    source_id: UUID | None
    ingestion_id: UUID | None
    intelligence_run_id: UUID | None
    created_at: datetime
    completed_at: datetime | None
    linked_service_case: LinkedServiceCase | None = None

    @field_serializer("created_at", "completed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class UserSubmissionListResponse(BaseModel):
    items: list[UserSubmissionSummary]
    limit: int
    offset: int


class SubmissionRecord(BaseModel):
    id: UUID
    status: SubmissionStatus
    failure_stage: SubmissionFailureStage | None
    input_type: SubmissionInputType
    input_content: str
    input_preview: str
    origin_type: SubmissionOriginType
    origin_discovery_id: UUID | None
    source_id: UUID | None
    ingestion_id: UUID | None
    intelligence_run_id: UUID | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @field_serializer("created_at", "updated_at", "completed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class SubmissionContentSummary(BaseModel):
    title: str | None
    publisher: str | None
    resolved_url: str | None
    excerpt: str | None
    fetch_status: str | None
    extraction_status: str | None
    warnings: list[str] = Field(default_factory=list)


class SubmissionIntelligenceSummary(BaseModel):
    run_id: UUID
    status: str
    result: ContentIntelligenceResult | None = None


class UserSubmissionDetail(BaseModel):
    submission: SubmissionRecord
    submitted_by: MeUser
    enterprise: MeEnterprise
    content: SubmissionContentSummary | None = None
    intelligence: SubmissionIntelligenceSummary | None = None
    linked_service_case: LinkedServiceCase | None = None
