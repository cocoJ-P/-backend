"""Discovery HTTP API. Requires development identity."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.discovery.enums import DiscoveryStatus
from app.domains.discovery.schemas import (
    AcceptDiscoveryResponse,
    CreateDiscoveryRequest,
    DiscoveryItemDetail,
    DiscoveryItemListResponse,
)
from app.domains.discovery.service import (
    create_discovery_item,
    get_discovery_item,
    list_discovery_items,
    withdraw_discovery_item,
)
from app.domains.discovery.user_state_schemas import (
    DiscoveryFeedResponse,
    DiscoveryUserStateResponse,
    UpdateDiscoveryUserStateRequest,
)
from app.domains.discovery.user_state_service import (
    get_current_user_state,
    list_discovery_feed,
    list_saved_discoveries,
    mark_discovery_seen,
    update_current_user_state,
)
from app.domains.discovery.accept_service import accept_discovery
from app.domains.identity.dependencies import get_current_identity
from app.domains.identity.schemas import CurrentIdentity

router = APIRouter(prefix="/discoveries", tags=["Discoveries"])


@router.post(
    "",
    response_model=DiscoveryItemDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_discovery(
    payload: CreateDiscoveryRequest,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> DiscoveryItemDetail:
    return create_discovery_item(db, identity, payload)


@router.get(
    "",
    response_model=DiscoveryItemListResponse,
)
def list_discoveries(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    status_filter: Annotated[DiscoveryStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> DiscoveryItemListResponse:
    return list_discovery_items(
        db,
        identity,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/feed",
    response_model=DiscoveryFeedResponse,
)
def list_discovery_feed_for_current_user(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> DiscoveryFeedResponse:
    return list_discovery_feed(db, identity, limit=limit, offset=offset)


@router.get(
    "/saved",
    response_model=DiscoveryFeedResponse,
)
def list_saved_discoveries_for_current_user(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> DiscoveryFeedResponse:
    return list_saved_discoveries(db, identity, limit=limit, offset=offset)


@router.get(
    "/{discovery_id}",
    response_model=DiscoveryItemDetail,
)
def get_discovery(
    discovery_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> DiscoveryItemDetail:
    return get_discovery_item(db, identity, discovery_id)


@router.post(
    "/{discovery_id}/withdraw",
    response_model=DiscoveryItemDetail,
)
def withdraw_discovery(
    discovery_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> DiscoveryItemDetail:
    return withdraw_discovery_item(db, identity, discovery_id)


@router.post(
    "/{discovery_id}/seen",
    response_model=DiscoveryUserStateResponse,
)
def mark_discovery_seen_for_current_user(
    discovery_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> DiscoveryUserStateResponse:
    return mark_discovery_seen(db, identity, discovery_id)


@router.post(
    "/{discovery_id}/accept",
    response_model=AcceptDiscoveryResponse,
)
def accept_discovery_for_current_user(
    discovery_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    response: Response,
    db: Session = Depends(get_db),
) -> AcceptDiscoveryResponse:
    result = accept_discovery(db, identity, discovery_id)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return result


@router.get(
    "/{discovery_id}/user-state",
    response_model=DiscoveryUserStateResponse,
)
def get_discovery_user_state_for_current_user(
    discovery_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> DiscoveryUserStateResponse:
    return get_current_user_state(db, identity, discovery_id)


@router.patch(
    "/{discovery_id}/user-state",
    response_model=DiscoveryUserStateResponse,
)
def update_discovery_user_state_for_current_user(
    discovery_id: UUID,
    payload: UpdateDiscoveryUserStateRequest,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> DiscoveryUserStateResponse:
    return update_current_user_state(db, identity, discovery_id, payload)
