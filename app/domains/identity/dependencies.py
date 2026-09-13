"""FastAPI dependency for development identity."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.domains.identity.schemas import CurrentIdentity
from app.domains.identity.service import resolve_current_identity

DEV_USER_HEADER = "X-Dev-User-Id"
DEV_USER_HEADER_DESCRIPTION = (
    "Development-only identity header. Not a production authentication mechanism."
)


def get_current_identity(
    x_dev_user_id: Annotated[
        str | None,
        Header(
            alias=DEV_USER_HEADER,
            description=DEV_USER_HEADER_DESCRIPTION,
        ),
    ] = None,
    db: Session = Depends(get_db),
) -> CurrentIdentity:
    if not settings.DEV_IDENTITY_ENABLED:
        raise AppException(
            "AUTHENTICATION_REQUIRED",
            "Authentication required",
            status_code=401,
        )
    if x_dev_user_id is None or not x_dev_user_id.strip():
        raise AppException(
            "DEV_IDENTITY_REQUIRED",
            "X-Dev-User-Id header is required",
            status_code=401,
        )
    try:
        user_id = UUID(x_dev_user_id.strip())
    except ValueError as exc:
        raise AppException(
            "INVALID_DEV_USER_ID",
            "X-Dev-User-Id must be a UUID",
            status_code=400,
        ) from exc
    return resolve_current_identity(db, user_id)
