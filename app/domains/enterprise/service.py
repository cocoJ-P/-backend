"""Enterprise domain services."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.core.time import ensure_utc, utc_now
from app.domains.enterprise import repository
from app.domains.enterprise.models import Enterprise, EnterpriseState
from app.domains.enterprise.schemas import EnterpriseCreate, EnterpriseStateCreate


def list_enterprises(db: Session) -> list[Enterprise]:
    return repository.list_enterprises(db)


def get_enterprise(db: Session, enterprise_id: UUID) -> Enterprise:
    enterprise = repository.get_enterprise(db, enterprise_id)
    if enterprise is None:
        raise NotFoundException(
            "Enterprise not found",
            code="ENTERPRISE_NOT_FOUND",
        )
    return enterprise


def get_latest_state(db: Session, enterprise_id: UUID) -> EnterpriseState:
    get_enterprise(db, enterprise_id)
    state = repository.get_latest_state(db, enterprise_id)
    if state is None:
        raise NotFoundException(
            "Enterprise state not found",
            code="ENTERPRISE_STATE_NOT_FOUND",
        )
    return state


def create_enterprise(db: Session, payload: EnterpriseCreate) -> Enterprise:
    enterprise = Enterprise(
        name=payload.name.strip(),
        registration_region=payload.registration_region,
        established_at=payload.established_at,
        enterprise_type=payload.enterprise_type.value,
        industry=payload.industry,
    )
    repository.add_enterprise(db, enterprise)
    db.commit()
    db.refresh(enterprise)
    return enterprise


def create_state(
    db: Session,
    enterprise_id: UUID,
    payload: EnterpriseStateCreate,
) -> EnterpriseState:
    get_enterprise(db, enterprise_id)
    effective_at = payload.effective_at or utc_now()
    state = EnterpriseState(
        enterprise_id=enterprise_id,
        product_stage=payload.product_stage.value,
        business_stage=payload.business_stage.value,
        team_size=payload.team_size,
        revenue_stage=payload.revenue_stage.value,
        funding_stage=payload.funding_stage.value,
        ip_count=payload.ip_count,
        qualifications=payload.qualifications,
        current_goal=payload.current_goal,
        current_constraint=payload.current_constraint,
        recent_events=payload.recent_events,
        available_materials=payload.available_materials,
        effective_at=ensure_utc(effective_at),
    )
    repository.add_state(db, state)
    db.commit()
    db.refresh(state)
    return state
