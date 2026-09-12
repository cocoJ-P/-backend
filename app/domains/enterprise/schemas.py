"""Pydantic schemas for the Enterprise domain."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.time import to_iso8601
from app.domains.enterprise.enums import (
    BusinessStage,
    EnterpriseType,
    FundingStage,
    ProductStage,
    RevenueStage,
)


class EnterpriseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    registration_region: str | None = Field(default=None, max_length=255)
    established_at: date | None = None
    enterprise_type: EnterpriseType
    industry: str | None = Field(default=None, max_length=128)


class EnterpriseListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    registration_region: str | None
    enterprise_type: EnterpriseType
    industry: str | None


class EnterpriseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    registration_region: str | None
    established_at: date | None
    enterprise_type: EnterpriseType
    industry: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso8601(value)


class EnterpriseStateCreate(BaseModel):
    product_stage: ProductStage
    business_stage: BusinessStage
    team_size: int | None = Field(default=None, ge=0)
    revenue_stage: RevenueStage
    funding_stage: FundingStage
    ip_count: int | None = Field(default=None, ge=0)
    qualifications: list[str] | None = None
    current_goal: str | None = None
    current_constraint: str | None = None
    recent_events: list[str] | None = None
    available_materials: list[str] | None = None
    effective_at: datetime | None = None


class EnterpriseStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    enterprise_id: UUID
    product_stage: ProductStage
    business_stage: BusinessStage
    team_size: int | None
    revenue_stage: RevenueStage
    funding_stage: FundingStage
    ip_count: int | None
    qualifications: list[str] | None
    current_goal: str | None
    current_constraint: str | None
    recent_events: list[str] | None
    available_materials: list[str] | None
    effective_at: datetime
    created_at: datetime

    @field_serializer("effective_at", "created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso8601(value)
