"""Idempotent Demo User and EnterpriseMember seed."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domains.enterprise.seed import DEMO_ENTERPRISE_ID, seed_demo_enterprise
from app.domains.identity.enums import (
    EnterpriseMemberRole,
    EnterpriseMemberStatus,
    UserStatus,
)
from app.domains.identity.models import EnterpriseMember, User
from app.domains.identity.repository import (
    create_membership,
    create_user,
    get_membership_for_user_enterprise,
    get_user_by_id,
)

DEMO_USER_ID = UUID("2d7c1f4a-8b3e-4a91-9c2d-6e5f4a3b2c10")
DEMO_MEMBERSHIP_ID = UUID("9a8b7c6d-5e4f-4a3b-2c1d-0e9f8a7b6c5d")


def seed_demo_identity(db: Session) -> User:
    seed_demo_enterprise(db)
    now = utc_now()
    user = get_user_by_id(db, DEMO_USER_ID)
    if user is None:
        user = User(
            id=DEMO_USER_ID,
            display_name="Demo User",
            status=UserStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        create_user(db, user)
    else:
        user.display_name = "Demo User"
        user.status = UserStatus.ACTIVE.value
        user.updated_at = now

    membership = get_membership_for_user_enterprise(db, DEMO_USER_ID, DEMO_ENTERPRISE_ID)
    if membership is None:
        membership = EnterpriseMember(
            id=DEMO_MEMBERSHIP_ID,
            user_id=DEMO_USER_ID,
            enterprise_id=DEMO_ENTERPRISE_ID,
            role=EnterpriseMemberRole.OWNER.value,
            status=EnterpriseMemberStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        create_membership(db, membership)
    else:
        membership.role = EnterpriseMemberRole.OWNER.value
        membership.status = EnterpriseMemberStatus.ACTIVE.value
        membership.updated_at = now

    db.commit()
    db.refresh(user)
    return user
