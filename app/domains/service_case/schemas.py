"""HTTP schemas for ServiceCase."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_serializer

from app.core.time import to_iso8601
from app.domains.service_case.enums import ServiceCaseStatus
from app.domains.submission.enums import SubmissionInputType, SubmissionOriginType, SubmissionStatus


class ServiceCaseActor(BaseModel):
    id: UUID
    display_name: str


class ServiceCaseRecord(BaseModel):
    id: UUID
    enterprise_id: UUID
    created_by_user_id: UUID
    submission_id: UUID
    title: str
    status: ServiceCaseStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    closed_at: datetime | None

    @field_serializer("created_at", "updated_at", "completed_at", "closed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class CreateServiceCaseResponse(BaseModel):
    created: bool
    service_case: ServiceCaseRecord


class LinkedServiceCase(BaseModel):
    id: UUID
    status: ServiceCaseStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    closed_at: datetime | None

    @field_serializer("created_at", "updated_at", "completed_at", "closed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class ServiceCaseListSubmissionRef(BaseModel):
    id: UUID
    status: SubmissionStatus
    origin_type: SubmissionOriginType
    origin_discovery_id: UUID | None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return to_iso8601(value)


class ServiceCaseListItem(BaseModel):
    id: UUID
    title: str
    status: ServiceCaseStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    closed_at: datetime | None
    created_by_user: ServiceCaseActor
    submission: ServiceCaseListSubmissionRef

    @field_serializer("created_at", "updated_at", "completed_at", "closed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class ServiceCaseListResponse(BaseModel):
    items: list[ServiceCaseListItem]
    limit: int
    offset: int


class ServiceCaseDetailSubmissionRef(BaseModel):
    id: UUID
    status: SubmissionStatus
    input_type: SubmissionInputType
    input_preview: str
    origin_type: SubmissionOriginType
    origin_discovery_id: UUID | None
    created_at: datetime
    completed_at: datetime | None

    @field_serializer("created_at", "completed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class ServiceCaseDetail(BaseModel):
    id: UUID
    enterprise_id: UUID
    created_by_user_id: UUID
    submission_id: UUID
    title: str
    status: ServiceCaseStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    closed_at: datetime | None
    created_by_user: ServiceCaseActor
    submission: ServiceCaseDetailSubmissionRef

    @field_serializer("created_at", "updated_at", "completed_at", "closed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)
