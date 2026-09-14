"""Enterprise-scoped DiscoveryUserState list. Requires development identity."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.discovery.enums import DiscoveryDisposition
from app.domains.discovery.user_state_schemas import DiscoveryUserStateListResponse
from app.domains.discovery.user_state_service import list_enterprise_user_states
from app.domains.identity.dependencies import get_current_identity
from app.domains.identity.schemas import CurrentIdentity

router = APIRouter(prefix="/discovery-user-states", tags=["Discovery User States"])


@router.get(
    "",
    response_model=DiscoveryUserStateListResponse,
)
def list_discovery_user_states(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    discovery_id: UUID | None = None,
    user_id: UUID | None = None,
    disposition: DiscoveryDisposition | None = None,
    seen: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> DiscoveryUserStateListResponse:
    return list_enterprise_user_states(
        db,
        identity,
        discovery_id=discovery_id,
        user_id=user_id,
        disposition=disposition,
        seen=seen,
        limit=limit,
        offset=offset,
    )
