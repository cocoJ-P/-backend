"""Enterprise database access."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.enterprise.models import Enterprise, EnterpriseState


def list_enterprises(db: Session) -> list[Enterprise]:
    statement = select(Enterprise).order_by(Enterprise.created_at.asc(), Enterprise.name.asc())
    return list(db.scalars(statement).all())


def get_enterprise(db: Session, enterprise_id: UUID) -> Enterprise | None:
    return db.get(Enterprise, enterprise_id)


def add_enterprise(db: Session, enterprise: Enterprise) -> Enterprise:
    db.add(enterprise)
    db.flush()
    db.refresh(enterprise)
    return enterprise


def get_latest_state(db: Session, enterprise_id: UUID) -> EnterpriseState | None:
    statement = (
        select(EnterpriseState)
        .where(EnterpriseState.enterprise_id == enterprise_id)
        .order_by(
            EnterpriseState.effective_at.desc(),
            EnterpriseState.created_at.desc(),
        )
        .limit(1)
    )
    return db.scalars(statement).first()


def add_state(db: Session, state: EnterpriseState) -> EnterpriseState:
    db.add(state)
    db.flush()
    db.refresh(state)
    return state
