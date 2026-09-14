"""Current-user DiscoveryUserState and user-aware feed.

Does not mutate DiscoveryItem.status. GET /feed is a pure read.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.discovery.enums import DiscoveryDisposition, DiscoveryPriority, DiscoveryReferenceType, DiscoveryStatus
from app.domains.discovery.models import DiscoveryItem
from app.domains.discovery.service import require_enterprise_discovery
from app.domains.discovery.user_state_models import DiscoveryUserState
from app.domains.discovery.user_state_repository import (
    get_or_create_user_state,
    get_user_state,
    list_feed_for_user,
    list_saved_for_user,
    list_user_states_for_enterprise,
    save_user_state,
)
from app.domains.discovery.user_state_schemas import (
    DiscoveryFeedItem,
    DiscoveryFeedResponse,
    DiscoveryFeedUserState,
    DiscoveryUserStateDiscoveryRef,
    DiscoveryUserStateListItem,
    DiscoveryUserStateListResponse,
    DiscoveryUserStateResponse,
    DiscoveryUserStateUserRef,
    LinkedDiscoverySubmission,
    UpdateDiscoveryUserStateRequest,
)
from app.domains.identity.models import User
from app.domains.identity.schemas import CurrentIdentity
from app.domains.opportunity.enums import OpportunityType
from app.domains.submission.enums import SubmissionFailureStage, SubmissionOriginType, SubmissionStatus
from app.domains.submission.models import UserSubmission

logger = get_logger(__name__)


def mark_discovery_seen(
    db: Session,
    identity: CurrentIdentity,
    discovery_id: UUID,
) -> DiscoveryUserStateResponse:
    discovery = require_enterprise_discovery(db, identity.enterprise_id, discovery_id)
    state = get_or_create_user_state(
        db,
        discovery_id=discovery.id,
        enterprise_id=discovery.enterprise_id,
        user_id=identity.user_id,
    )
    if state.seen_at is None:
        state.seen_at = utc_now()
        save_user_state(db, state)
        logger.info(
            "discovery marked seen discovery_id=%s user_id=%s enterprise_id=%s first=true",
            discovery.id,
            identity.user_id,
            identity.enterprise_id,
        )
    else:
        logger.info(
            "discovery marked seen discovery_id=%s user_id=%s enterprise_id=%s first=false",
            discovery.id,
            identity.user_id,
            identity.enterprise_id,
        )
    return _to_state_response(state)


def get_current_user_state(
    db: Session,
    identity: CurrentIdentity,
    discovery_id: UUID,
) -> DiscoveryUserStateResponse:
    require_enterprise_discovery(db, identity.enterprise_id, discovery_id)
    state = get_user_state(db, discovery_id, identity.user_id)
    if state is None:
        return DiscoveryUserStateResponse(
            discovery_id=discovery_id,
            user_id=identity.user_id,
            seen_at=None,
            disposition=None,
            disposition_at=None,
            updated_at=None,
        )
    return _to_state_response(state)


def update_current_user_state(
    db: Session,
    identity: CurrentIdentity,
    discovery_id: UUID,
    payload: UpdateDiscoveryUserStateRequest,
) -> DiscoveryUserStateResponse:
    discovery = require_enterprise_discovery(db, identity.enterprise_id, discovery_id)
    new_disposition = None if payload.disposition is None else payload.disposition.value
    existing = get_user_state(db, discovery.id, identity.user_id)
    if existing is None and new_disposition is None:
        return DiscoveryUserStateResponse(
            discovery_id=discovery.id,
            user_id=identity.user_id,
            seen_at=None,
            disposition=None,
            disposition_at=None,
            updated_at=None,
        )

    state = existing or get_or_create_user_state(
        db,
        discovery_id=discovery.id,
        enterprise_id=discovery.enterprise_id,
        user_id=identity.user_id,
    )
    old_disposition = state.disposition
    now = utc_now()
    changed = False
    if new_disposition is None:
        if state.disposition is not None:
            state.disposition = None
            state.disposition_at = None
            changed = True
    elif state.disposition != new_disposition:
        state.disposition = new_disposition
        state.disposition_at = now
        changed = True
    if new_disposition is not None and state.seen_at is None:
        state.seen_at = now
        changed = True
    if changed:
        save_user_state(db, state)
    logger.info(
        "discovery user-state updated discovery_id=%s user_id=%s enterprise_id=%s "
        "old_disposition=%s new_disposition=%s",
        discovery.id,
        identity.user_id,
        identity.enterprise_id,
        old_disposition,
        state.disposition,
    )
    return _to_state_response(state)


def list_discovery_feed(
    db: Session,
    identity: CurrentIdentity,
    *,
    limit: int = 20,
    offset: int = 0,
) -> DiscoveryFeedResponse:
    rows = list_feed_for_user(
        db,
        enterprise_id=identity.enterprise_id,
        user_id=identity.user_id,
        limit=limit,
        offset=offset,
    )
    return DiscoveryFeedResponse(
        items=[_to_feed_item(item, state) for item, state in rows],
        limit=limit,
        offset=offset,
    )


def list_saved_discoveries(
    db: Session,
    identity: CurrentIdentity,
    *,
    limit: int = 20,
    offset: int = 0,
) -> DiscoveryFeedResponse:
    rows = list_saved_for_user(
        db,
        enterprise_id=identity.enterprise_id,
        user_id=identity.user_id,
        limit=limit,
        offset=offset,
    )
    return DiscoveryFeedResponse(
        items=[_to_feed_item(item, state) for item, state in rows],
        limit=limit,
        offset=offset,
    )


def list_enterprise_user_states(
    db: Session,
    identity: CurrentIdentity,
    *,
    discovery_id: UUID | None = None,
    user_id: UUID | None = None,
    disposition: DiscoveryDisposition | None = None,
    seen: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> DiscoveryUserStateListResponse:
    rows = list_user_states_for_enterprise(
        db,
        identity.enterprise_id,
        discovery_id=discovery_id,
        user_id=user_id,
        disposition=None if disposition is None else disposition.value,
        seen=seen,
        limit=limit,
        offset=offset,
    )
    discoveries = _load_discoveries(db, {state.discovery_id for state, _submission in rows})
    users = _load_users(db, {state.user_id for state, _submission in rows})
    items: list[DiscoveryUserStateListItem] = []
    for state, submission in rows:
        discovery = discoveries.get(state.discovery_id)
        user = users.get(state.user_id)
        if discovery is None or user is None:
            continue
        items.append(
            DiscoveryUserStateListItem(
                id=state.id,
                discovery=DiscoveryUserStateDiscoveryRef(
                    id=discovery.id,
                    title=discovery.title,
                    status=DiscoveryStatus(discovery.status),
                    reference_type=DiscoveryReferenceType(discovery.reference_type),
                ),
                user=DiscoveryUserStateUserRef(id=user.id, display_name=user.display_name),
                seen_at=state.seen_at,
                disposition=state.disposition,
                disposition_at=state.disposition_at,
                created_at=state.created_at,
                updated_at=state.updated_at,
                linked_submission=_to_linked_submission(submission),
            )
        )
    return DiscoveryUserStateListResponse(items=items, limit=limit, offset=offset)


def _to_state_response(state: DiscoveryUserState) -> DiscoveryUserStateResponse:
    return DiscoveryUserStateResponse(
        discovery_id=state.discovery_id,
        user_id=state.user_id,
        seen_at=state.seen_at,
        disposition=state.disposition,
        disposition_at=state.disposition_at,
        updated_at=state.updated_at,
    )


def _to_linked_submission(submission: UserSubmission | None) -> LinkedDiscoverySubmission | None:
    if submission is None:
        return None
    failure_stage = None
    if submission.failure_stage:
        failure_stage = SubmissionFailureStage(submission.failure_stage)
    return LinkedDiscoverySubmission(
        id=submission.id,
        status=SubmissionStatus(submission.status),
        origin_type=SubmissionOriginType(submission.origin_type),
        created_at=submission.created_at,
        completed_at=submission.completed_at,
        failure_stage=failure_stage,
        error_code=submission.error_code,
        error_message=submission.error_message,
    )


def _to_feed_item(item: DiscoveryItem, state: DiscoveryUserState | None) -> DiscoveryFeedItem:
    opportunity_type = None
    if item.opportunity_type:
        opportunity_type = OpportunityType(item.opportunity_type)
    current = None
    if state is not None:
        current = DiscoveryFeedUserState(
            seen_at=state.seen_at,
            disposition=state.disposition,
            disposition_at=state.disposition_at,
        )
    return DiscoveryFeedItem(
        id=item.id,
        status=DiscoveryStatus(item.status),
        priority=DiscoveryPriority(item.priority),
        reference_type=DiscoveryReferenceType(item.reference_type),
        title=item.title,
        summary=item.summary,
        reason=item.reason,
        opportunity_type=opportunity_type,
        issuer=item.issuer,
        region=item.region,
        deadline=item.deadline,
        reference_url=item.reference_url,
        created_at=item.created_at,
        current_user_state=current,
    )


def _load_discoveries(db: Session, discovery_ids: set[UUID]) -> dict[UUID, DiscoveryItem]:
    if not discovery_ids:
        return {}
    rows = db.scalars(select(DiscoveryItem).where(DiscoveryItem.id.in_(discovery_ids))).all()
    return {row.id: row for row in rows}


def _load_users(db: Session, user_ids: set[UUID]) -> dict[UUID, User]:
    if not user_ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(user_ids))).all()
    return {row.id: row for row in rows}
