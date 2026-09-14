"""Persistence for DiscoveryUserState and the current-user feed query."""

from uuid import UUID

from sqlalchemy import and_, case, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domains.discovery.enums import DiscoveryStatus
from app.domains.discovery.models import DiscoveryItem
from app.domains.discovery.repository import PRIORITY_ORDER
from app.domains.discovery.user_state_models import DiscoveryUserState
from app.domains.submission.enums import SubmissionOriginType
from app.domains.submission.models import UserSubmission

FEED_EXCLUDED_DISPOSITIONS = {"saved"}

FEED_BUCKET = case(
    (
        DiscoveryUserState.id.is_(None)
        | and_(DiscoveryUserState.disposition.is_(None), DiscoveryUserState.seen_at.is_(None)),
        0,
    ),
    (DiscoveryUserState.disposition.is_(None), 1),
    (DiscoveryUserState.disposition == "deprioritized", 2),
    else_=3,
)


def get_user_state(
    db: Session,
    discovery_id: UUID,
    user_id: UUID,
) -> DiscoveryUserState | None:
    statement = select(DiscoveryUserState).where(
        DiscoveryUserState.discovery_id == discovery_id,
        DiscoveryUserState.user_id == user_id,
    )
    return db.scalars(statement).first()


def get_or_create_user_state(
    db: Session,
    *,
    discovery_id: UUID,
    enterprise_id: UUID,
    user_id: UUID,
) -> DiscoveryUserState:
    existing = get_user_state(db, discovery_id, user_id)
    if existing is not None:
        return existing
    now = utc_now()
    row = DiscoveryUserState(
        discovery_id=discovery_id,
        enterprise_id=enterprise_id,
        user_id=user_id,
        seen_at=None,
        disposition=None,
        disposition_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        existing = get_user_state(db, discovery_id, user_id)
        if existing is None:
            raise
        return existing


def save_user_state(db: Session, state: DiscoveryUserState) -> DiscoveryUserState:
    state.updated_at = utc_now()
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def list_user_states_for_enterprise(
    db: Session,
    enterprise_id: UUID,
    *,
    discovery_id: UUID | None = None,
    user_id: UUID | None = None,
    disposition: str | None = None,
    seen: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[tuple[DiscoveryUserState, UserSubmission | None]]:
    statement = (
        select(DiscoveryUserState, UserSubmission)
        .outerjoin(
            UserSubmission,
            and_(
                UserSubmission.enterprise_id == DiscoveryUserState.enterprise_id,
                UserSubmission.user_id == DiscoveryUserState.user_id,
                UserSubmission.origin_discovery_id == DiscoveryUserState.discovery_id,
                UserSubmission.origin_type == SubmissionOriginType.DISCOVERY.value,
            ),
        )
        .where(DiscoveryUserState.enterprise_id == enterprise_id)
    )
    if discovery_id is not None:
        statement = statement.where(DiscoveryUserState.discovery_id == discovery_id)
    if user_id is not None:
        statement = statement.where(DiscoveryUserState.user_id == user_id)
    if disposition is not None:
        statement = statement.where(DiscoveryUserState.disposition == disposition)
    if seen is True:
        statement = statement.where(DiscoveryUserState.seen_at.is_not(None))
    elif seen is False:
        statement = statement.where(DiscoveryUserState.seen_at.is_(None))
    statement = (
        statement.order_by(DiscoveryUserState.updated_at.desc(), DiscoveryUserState.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [(state, submission) for state, submission in db.execute(statement).all()]


def list_feed_for_user(
    db: Session,
    *,
    enterprise_id: UUID,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[tuple[DiscoveryItem, DiscoveryUserState | None]]:
    statement = (
        select(DiscoveryItem, DiscoveryUserState)
        .outerjoin(
            DiscoveryUserState,
            and_(
                DiscoveryUserState.discovery_id == DiscoveryItem.id,
                DiscoveryUserState.user_id == user_id,
            ),
        )
        .where(DiscoveryItem.enterprise_id == enterprise_id)
        .where(DiscoveryItem.status == DiscoveryStatus.ACTIVE.value)
        .where(
            or_(
                DiscoveryUserState.id.is_(None),
                DiscoveryUserState.disposition.is_(None),
                DiscoveryUserState.disposition == "deprioritized",
            )
        )
        .order_by(
            FEED_BUCKET,
            PRIORITY_ORDER,
            DiscoveryItem.created_at.desc(),
            DiscoveryItem.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    rows = db.execute(statement).all()
    return [(item, state) for item, state in rows]


def list_saved_for_user(
    db: Session,
    *,
    enterprise_id: UUID,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[tuple[DiscoveryItem, DiscoveryUserState]]:
    statement = (
        select(DiscoveryItem, DiscoveryUserState)
        .join(
            DiscoveryUserState,
            and_(
                DiscoveryUserState.discovery_id == DiscoveryItem.id,
                DiscoveryUserState.user_id == user_id,
            ),
        )
        .where(DiscoveryItem.enterprise_id == enterprise_id)
        .where(DiscoveryItem.status == DiscoveryStatus.ACTIVE.value)
        .where(DiscoveryUserState.disposition == "saved")
        .order_by(
            DiscoveryUserState.disposition_at.desc(),
            PRIORITY_ORDER,
            DiscoveryItem.created_at.desc(),
            DiscoveryItem.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    rows = db.execute(statement).all()
    return [(item, state) for item, state in rows]
