"""Opportunity HTTP API."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.opportunity import service
from app.domains.opportunity.enums import OpportunityType
from app.domains.opportunity.schemas import (
    OpportunityCreate,
    OpportunityListItem,
    OpportunityRequirementCreate,
    OpportunityRequirementResponse,
    OpportunityResponse,
    OpportunitySourceCreate,
    OpportunitySourceResponse,
)

router = APIRouter(tags=["Opportunities"])
source_router = APIRouter(tags=["Opportunity Sources"])


@router.get("/opportunities", response_model=list[OpportunityListItem])
def list_opportunities(
    type: OpportunityType | None = None,
    db: Session = Depends(get_db),
) -> list[OpportunityListItem]:
    return service.list_opportunities(db, opportunity_type=type)


@router.post(
    "/opportunities",
    response_model=OpportunityResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_opportunity(
    payload: OpportunityCreate,
    db: Session = Depends(get_db),
) -> OpportunityResponse:
    return service.create_opportunity(db, payload)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity(
    opportunity_id: UUID,
    db: Session = Depends(get_db),
) -> OpportunityResponse:
    return service.get_opportunity(db, opportunity_id)


@router.get(
    "/opportunities/{opportunity_id}/sources",
    response_model=list[OpportunitySourceResponse],
)
def list_opportunity_sources(
    opportunity_id: UUID,
    db: Session = Depends(get_db),
) -> list[OpportunitySourceResponse]:
    return service.list_sources(db, opportunity_id)


@router.post(
    "/opportunities/{opportunity_id}/sources",
    response_model=OpportunitySourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_opportunity_source(
    opportunity_id: UUID,
    payload: OpportunitySourceCreate,
    db: Session = Depends(get_db),
) -> OpportunitySourceResponse:
    return service.create_source(db, payload, opportunity_id=opportunity_id)


@router.get(
    "/opportunities/{opportunity_id}/requirements",
    response_model=list[OpportunityRequirementResponse],
)
def list_opportunity_requirements(
    opportunity_id: UUID,
    db: Session = Depends(get_db),
) -> list[OpportunityRequirementResponse]:
    return service.list_requirements(db, opportunity_id)


@router.post(
    "/opportunities/{opportunity_id}/requirements",
    response_model=OpportunityRequirementResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_opportunity_requirement(
    opportunity_id: UUID,
    payload: OpportunityRequirementCreate,
    db: Session = Depends(get_db),
) -> OpportunityRequirementResponse:
    return service.create_requirement(db, opportunity_id, payload)


@source_router.post(
    "/opportunity-sources",
    response_model=OpportunitySourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_opportunity_source(
    payload: OpportunitySourceCreate,
    db: Session = Depends(get_db),
) -> OpportunitySourceResponse:
    return service.create_source(db, payload)
