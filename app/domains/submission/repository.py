"""UserSubmission persistence. Routes must not query this table directly."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domains.submission.models import UserSubmission


def create_submission(db: Session, submission: UserSubmission) -> UserSubmission:
    add_submission(db, submission)
    db.commit()
    db.refresh(submission)
    return submission


def add_submission(db: Session, submission: UserSubmission) -> UserSubmission:
    db.add(submission)
    db.flush()
    db.refresh(submission)
    return submission


def get_submission_by_id(db: Session, submission_id: UUID) -> UserSubmission | None:
    return db.get(UserSubmission, submission_id)


def get_submission_for_enterprise(
    db: Session,
    submission_id: UUID,
    enterprise_id: UUID,
) -> UserSubmission | None:
    statement = select(UserSubmission).where(
        UserSubmission.id == submission_id,
        UserSubmission.enterprise_id == enterprise_id,
    )
    return db.scalars(statement).first()


def get_submission_for_owner(
    db: Session,
    submission_id: UUID,
    *,
    enterprise_id: UUID,
    user_id: UUID,
) -> UserSubmission | None:
    statement = select(UserSubmission).where(
        UserSubmission.id == submission_id,
        UserSubmission.enterprise_id == enterprise_id,
        UserSubmission.user_id == user_id,
    )
    return db.scalars(statement).first()


def list_submissions_for_enterprise(
    db: Session,
    enterprise_id: UUID,
    *,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[UserSubmission]:
    statement = select(UserSubmission).where(UserSubmission.enterprise_id == enterprise_id)
    if status is not None:
        statement = statement.where(UserSubmission.status == status)
    statement = (
        statement.order_by(UserSubmission.created_at.desc(), UserSubmission.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def get_discovery_origin_submission(
    db: Session,
    *,
    enterprise_id: UUID,
    user_id: UUID,
    origin_discovery_id: UUID,
) -> UserSubmission | None:
    statement = select(UserSubmission).where(
        UserSubmission.enterprise_id == enterprise_id,
        UserSubmission.user_id == user_id,
        UserSubmission.origin_discovery_id == origin_discovery_id,
    )
    return db.scalars(statement).first()


def list_submissions_for_user(
    db: Session,
    *,
    enterprise_id: UUID,
    user_id: UUID,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[UserSubmission]:
    statement = select(UserSubmission).where(
        UserSubmission.enterprise_id == enterprise_id,
        UserSubmission.user_id == user_id,
    )
    if status is not None:
        statement = statement.where(UserSubmission.status == status)
    statement = (
        statement.order_by(UserSubmission.created_at.desc(), UserSubmission.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def save_submission(db: Session, submission: UserSubmission) -> UserSubmission:
    submission.updated_at = utc_now()
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission
