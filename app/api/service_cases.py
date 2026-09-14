"""ServiceCase HTTP API. Requires development identity."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.identity.dependencies import get_current_identity
from app.domains.identity.schemas import CurrentIdentity
from app.domains.service_case.enums import ServiceCaseStatus
from app.domains.service_case.schemas import ServiceCaseDetail, ServiceCaseListResponse
from app.domains.service_case.service import (
    get_service_case_detail,
    list_enterprise_service_cases,
    list_my_service_cases,
)

router = APIRouter(prefix="/service-cases", tags=["Service Cases"])


@router.get(
    "",
    response_model=ServiceCaseListResponse,
)
def list_service_cases(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    status_filter: Annotated[ServiceCaseStatus | None, Query(alias="status")] = None,
    user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> ServiceCaseListResponse:
    return list_enterprise_service_cases(
        db,
        identity,
        status=status_filter,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/mine",
    response_model=ServiceCaseListResponse,
)
def list_my_service_cases_for_current_user(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    status_filter: Annotated[ServiceCaseStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> ServiceCaseListResponse:
    return list_my_service_cases(
        db,
        identity,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{service_case_id}",
    response_model=ServiceCaseDetail,
)
def get_service_case(
    service_case_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> ServiceCaseDetail:
    return get_service_case_detail(db, identity, service_case_id)
