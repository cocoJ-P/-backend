"""Resolve development identity and build /api/me responses."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.core.logging import get_logger
from app.domains.enterprise.repository import get_enterprise
from app.domains.identity.enums import EnterpriseMemberRole, UserStatus
from app.domains.identity.repository import (
    get_active_memberships_for_user,
    get_user_by_id,
)
from app.domains.identity.schemas import (
    CurrentIdentity,
    MeEnterprise,
    MeMembership,
    MeResponse,
    MeUser,
)

logger = get_logger(__name__)


def resolve_current_identity(db: Session, user_id: UUID) -> CurrentIdentity:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundException("User not found", code="USER_NOT_FOUND")
    if user.status != UserStatus.ACTIVE.value:
        raise AppException("USER_DISABLED", "User is disabled", status_code=403)

    memberships = get_active_memberships_for_user(db, user.id)
    if not memberships:
        raise AppException(
            "ENTERPRISE_MEMBERSHIP_NOT_FOUND",
            "No active enterprise membership",
            status_code=403,
        )
    if len(memberships) > 1:
        raise AppException(
            "ENTERPRISE_CONTEXT_REQUIRED",
            "Multiple active enterprise memberships",
            status_code=409,
        )

    membership = memberships[0]
    logger.info(
        "resolved identity user_id=%s enterprise_id=%s membership_id=%s role=%s",
        user.id,
        membership.enterprise_id,
        membership.id,
        membership.role,
    )
    return CurrentIdentity(
        user_id=user.id,
        enterprise_id=membership.enterprise_id,
        membership_id=membership.id,
        role=EnterpriseMemberRole(membership.role),
    )


def get_me(db: Session, identity: CurrentIdentity) -> MeResponse:
    user = get_user_by_id(db, identity.user_id)
    if user is None:
        raise NotFoundException("User not found", code="USER_NOT_FOUND")
    enterprise = get_enterprise(db, identity.enterprise_id)
    if enterprise is None:
        raise NotFoundException("Enterprise not found", code="ENTERPRISE_NOT_FOUND")
    memberships = get_active_memberships_for_user(db, identity.user_id)
    membership = next(
        (item for item in memberships if item.id == identity.membership_id),
        None,
    )
    if membership is None:
        raise AppException(
            "ENTERPRISE_MEMBERSHIP_NOT_FOUND",
            "No active enterprise membership",
            status_code=403,
        )
    return MeResponse(
        user=MeUser.model_validate(user),
        enterprise=MeEnterprise.model_validate(enterprise),
        membership=MeMembership.model_validate(membership),
    )
