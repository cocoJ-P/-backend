"""Enterprise HTTP API."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.enterprise import service
from app.domains.enterprise.schemas import (
    EnterpriseCreate,
    EnterpriseListItem,
    EnterpriseResponse,
    EnterpriseStateCreate,
    EnterpriseStateResponse,
)

router = APIRouter(tags=["Enterprises"])


@router.get("/enterprises", response_model=list[EnterpriseListItem])
def list_enterprises(db: Session = Depends(get_db)) -> list[EnterpriseListItem]:
    return service.list_enterprises(db)


@router.post(
    "/enterprises",
    response_model=EnterpriseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_enterprise(
    payload: EnterpriseCreate,
    db: Session = Depends(get_db),
) -> EnterpriseResponse:
    return service.create_enterprise(db, payload)


@router.get("/enterprises/{enterprise_id}", response_model=EnterpriseResponse)
def get_enterprise(
    enterprise_id: UUID,
    db: Session = Depends(get_db),
) -> EnterpriseResponse:
    return service.get_enterprise(db, enterprise_id)


@router.get(
    "/enterprises/{enterprise_id}/state",
    response_model=EnterpriseStateResponse,
)
def get_enterprise_state(
    enterprise_id: UUID,
    db: Session = Depends(get_db),
) -> EnterpriseStateResponse:
    return service.get_latest_state(db, enterprise_id)


@router.post(
    "/enterprises/{enterprise_id}/states",
    response_model=EnterpriseStateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_enterprise_state(
    enterprise_id: UUID,
    payload: EnterpriseStateCreate,
    db: Session = Depends(get_db),
) -> EnterpriseStateResponse:
    return service.create_state(db, enterprise_id, payload)
