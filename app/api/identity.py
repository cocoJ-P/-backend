"""Development identity HTTP API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.identity.dependencies import get_current_identity
from app.domains.identity.schemas import CurrentIdentity, MeResponse
from app.domains.identity.service import get_me

router = APIRouter(tags=["Identity"])


@router.get("/me", response_model=MeResponse)
def read_me(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> MeResponse:
    return get_me(db, identity)
