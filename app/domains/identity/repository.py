"""Identity database access."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.identity.enums import EnterpriseMemberStatus
from app.domains.identity.models import EnterpriseMember, User


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.get(User, user_id)


def get_active_memberships_for_user(db: Session, user_id: UUID) -> list[EnterpriseMember]:
    statement = (
        select(EnterpriseMember)
        .where(
            EnterpriseMember.user_id == user_id,
            EnterpriseMember.status == EnterpriseMemberStatus.ACTIVE.value,
        )
        .order_by(EnterpriseMember.created_at.asc())
    )
    return list(db.scalars(statement).all())


def get_membership_for_user_enterprise(
    db: Session,
    user_id: UUID,
    enterprise_id: UUID,
) -> EnterpriseMember | None:
    statement = select(EnterpriseMember).where(
        EnterpriseMember.user_id == user_id,
        EnterpriseMember.enterprise_id == enterprise_id,
    )
    return db.scalars(statement).first()


def create_user(db: Session, user: User) -> User:
    db.add(user)
    db.flush()
    db.refresh(user)
    return user


def create_membership(db: Session, membership: EnterpriseMember) -> EnterpriseMember:
    db.add(membership)
    db.flush()
    db.refresh(membership)
    return membership
