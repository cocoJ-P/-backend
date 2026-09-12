"""Pydantic schemas for the Opportunity domain."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.time import to_iso8601
from app.domains.opportunity.enums import (
    OpportunityStatus,
    OpportunityType,
    RequirementOperator,
    SourceType,
)


class OpportunityCreate(BaseModel):
    type: OpportunityType
    title: str = Field(min_length=1, max_length=512)
    issuer: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=255)
    publish_date: date | None = None
    deadline: date | None = None
    status: OpportunityStatus = OpportunityStatus.DRAFT
    official_url: str | None = Field(default=None, max_length=1024)
    summary: str | None = None
    resource_value: dict[str, Any] | None = None
    required_materials: list[str] | None = None
    application_process: list[str] | None = None


class OpportunityListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: OpportunityType
    title: str
    issuer: str | None
    region: str | None
    deadline: date | None
    status: OpportunityStatus


class OpportunitySourceCreate(BaseModel):
    opportunity_id: UUID | None = None
    source_type: SourceType
    title: str = Field(min_length=1, max_length=512)
    publisher: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=1024)
    published_at: datetime | None = None
    content_excerpt: str | None = None


class OpportunitySourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    opportunity_id: UUID | None
    source_type: SourceType
    title: str | None
    publisher: str | None
    url: str | None
    published_at: datetime | None
    content_excerpt: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("published_at", "created_at", "updated_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_iso8601(value)


class OpportunityRequirementCreate(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=255)
    operator: RequirementOperator
    expected_value: Any = None
    required: bool = True
    description: str | None = None
    source_reference: str | None = Field(default=None, max_length=255)


class OpportunityRequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    opportunity_id: UUID
    key: str
    label: str
    operator: RequirementOperator
    expected_value: Any
    required: bool
    description: str | None
    source_reference: str | None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso8601(value)


class OpportunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: OpportunityType
    title: str
    issuer: str | None
    region: str | None
    publish_date: date | None
    deadline: date | None
    status: OpportunityStatus
    official_url: str | None
    summary: str | None
    resource_value: dict[str, Any] | None
    required_materials: list[str] | None
    application_process: list[str] | None
    sources: list[OpportunitySourceResponse] = Field(default_factory=list)
    requirements: list[OpportunityRequirementResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso8601(value)
