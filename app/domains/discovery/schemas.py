"""HTTP schemas for DiscoveryItem.

Create uses a discriminated union so OpenAPI can express the three
reference types and extra fields cannot spoof identity or overwrite snapshots.
"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.time import to_iso8601
from app.domains.discovery.enums import (
    DiscoveryPriority,
    DiscoveryReferenceType,
    DiscoveryStatus,
)
from app.domains.opportunity.enums import OpportunityType
from app.domains.discovery.user_state_schemas import DiscoveryUserStateResponse
from app.domains.submission.schemas import UserSubmissionCreateResponse


class DiscoveryActor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str


class CreateOpportunityDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: Literal[DiscoveryReferenceType.OPPORTUNITY]
    opportunity_id: UUID
    reason: str | None = None
    priority: DiscoveryPriority = DiscoveryPriority.NORMAL


class CreateSourceDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: Literal[DiscoveryReferenceType.SOURCE]
    source_id: UUID
    reason: str | None = None
    priority: DiscoveryPriority = DiscoveryPriority.NORMAL


class CreateManualDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: Literal[DiscoveryReferenceType.MANUAL]
    title: str
    summary: str | None = None
    reason: str | None = None
    priority: DiscoveryPriority = DiscoveryPriority.NORMAL


CreateDiscoveryRequest = Annotated[
    CreateOpportunityDiscoveryRequest | CreateSourceDiscoveryRequest | CreateManualDiscoveryRequest,
    Field(discriminator="reference_type"),
]


class DiscoveryItemSummary(BaseModel):
    id: UUID
    status: DiscoveryStatus
    priority: DiscoveryPriority
    reference_type: DiscoveryReferenceType
    opportunity_id: UUID | None
    source_id: UUID | None
    title: str
    summary: str | None
    reason: str | None
    opportunity_type: OpportunityType | None
    issuer: str | None
    region: str | None
    deadline: date | None
    reference_url: str | None
    created_by: DiscoveryActor | None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return to_iso8601(value)


class DiscoveryItemDetail(DiscoveryItemSummary):
    updated_at: datetime
    withdrawn_at: datetime | None

    @field_serializer("updated_at", "withdrawn_at")
    def serialize_optional_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class DiscoveryItemListResponse(BaseModel):
    items: list[DiscoveryItemSummary]
    limit: int
    offset: int


class AcceptDiscoveryResponse(BaseModel):
    created: bool
    user_state: DiscoveryUserStateResponse
    submission: UserSubmissionCreateResponse
