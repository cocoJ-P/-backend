"""ServiceCase persistence. Routes must not query this table directly."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domains.identity.models import User
from app.domains.service_case.models import ServiceCase
from app.domains.submission.models import UserSubmission


def add_service_case(db: Session, case: ServiceCase) -> ServiceCase:
    db.add(case)
    db.flush()
    db.refresh(case)
    return case


def save_service_case(db: Session, case: ServiceCase) -> ServiceCase:
    case.updated_at = utc_now()
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def get_service_case_by_id(db: Session, service_case_id: UUID) -> ServiceCase | None:
    return db.get(ServiceCase, service_case_id)


def get_service_case_for_enterprise(
    db: Session,
    service_case_id: UUID,
    enterprise_id: UUID,
) -> ServiceCase | None:
    statement = select(ServiceCase).where(
        ServiceCase.id == service_case_id,
        ServiceCase.enterprise_id == enterprise_id,
    )
    return db.scalars(statement).first()


def get_service_case_by_submission_id(
    db: Session,
    submission_id: UUID,
) -> ServiceCase | None:
    statement = select(ServiceCase).where(ServiceCase.submission_id == submission_id)
    return db.scalars(statement).first()


def get_cases_by_submission_ids(
    db: Session,
    submission_ids: set[UUID],
) -> dict[UUID, ServiceCase]:
    if not submission_ids:
        return {}
    rows = db.scalars(select(ServiceCase).where(ServiceCase.submission_id.in_(submission_ids))).all()
    return {row.submission_id: row for row in rows}


def list_service_cases_for_enterprise(
    db: Session,
    enterprise_id: UUID,
    *,
    status: str | None = None,
    created_by_user_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[tuple[ServiceCase, User, UserSubmission]]:
    statement = (
        select(ServiceCase, User, UserSubmission)
        .join(User, User.id == ServiceCase.created_by_user_id)
        .join(UserSubmission, UserSubmission.id == ServiceCase.submission_id)
        .where(ServiceCase.enterprise_id == enterprise_id)
    )
    if status is not None:
        statement = statement.where(ServiceCase.status == status)
    if created_by_user_id is not None:
        statement = statement.where(ServiceCase.created_by_user_id == created_by_user_id)
    statement = (
        statement.order_by(ServiceCase.created_at.desc(), ServiceCase.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [(case, user, submission) for case, user, submission in db.execute(statement).all()]
