"""HTTP schemas for DiscoveryUserState and the user-aware feed."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer

from app.core.time import to_iso8601
from app.domains.discovery.enums import (
    DiscoveryDisposition,
    DiscoveryPriority,
    DiscoveryReferenceType,
    DiscoveryStatus,
)
from app.domains.opportunity.enums import OpportunityType
from app.domains.submission.enums import (
    SubmissionFailureStage,
    SubmissionOriginType,
    SubmissionStatus,
)


class UpdateDiscoveryUserStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: DiscoveryDisposition | None


class DiscoveryUserStateResponse(BaseModel):
    discovery_id: UUID
    user_id: UUID
    seen_at: datetime | None = None
    disposition: DiscoveryDisposition | None = None
    disposition_at: datetime | None = None
    updated_at: datetime | None = None

    @field_serializer("seen_at", "disposition_at", "updated_at")
    def serialize_optional_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class DiscoveryFeedUserState(BaseModel):
    seen_at: datetime | None = None
    disposition: DiscoveryDisposition | None = None
    disposition_at: datetime | None = None

    @field_serializer("seen_at", "disposition_at")
    def serialize_optional_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class DiscoveryFeedItem(BaseModel):
    id: UUID
    status: DiscoveryStatus
    priority: DiscoveryPriority
    reference_type: DiscoveryReferenceType
    title: str
    summary: str | None
    reason: str | None
    opportunity_type: OpportunityType | None
    issuer: str | None
    region: str | None
    deadline: date | None
    reference_url: str | None
    created_at: datetime
    current_user_state: DiscoveryFeedUserState | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return to_iso8601(value)


class DiscoveryFeedResponse(BaseModel):
    items: list[DiscoveryFeedItem]
    limit: int
    offset: int


class DiscoveryUserStateDiscoveryRef(BaseModel):
    id: UUID
    title: str
    status: DiscoveryStatus
    reference_type: DiscoveryReferenceType


class DiscoveryUserStateUserRef(BaseModel):
    id: UUID
    display_name: str


class LinkedDiscoverySubmission(BaseModel):
    id: UUID
    status: SubmissionStatus
    origin_type: SubmissionOriginType
    created_at: datetime
    completed_at: datetime | None
    failure_stage: SubmissionFailureStage | None = None
    error_code: str | None = None
    error_message: str | None = None

    @field_serializer("created_at", "completed_at")
    def serialize_optional_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class DiscoveryUserStateListItem(BaseModel):
    id: UUID
    discovery: DiscoveryUserStateDiscoveryRef
    user: DiscoveryUserStateUserRef
    seen_at: datetime | None
    disposition: DiscoveryDisposition | None
    disposition_at: datetime | None
    created_at: datetime
    updated_at: datetime
    linked_submission: LinkedDiscoverySubmission | None = None

    @field_serializer("seen_at", "disposition_at", "created_at", "updated_at")
    def serialize_optional_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class DiscoveryUserStateListResponse(BaseModel):
    items: list[DiscoveryUserStateListItem]
    limit: int
    offset: int
