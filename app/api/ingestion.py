"""Content ingestion HTTP API."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.content.schemas import IngestRequest, IngestResponse
from app.integrations.content.service import ingest

router = APIRouter(tags=["Content Ingestion"])


@router.post(
    "/content/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_content(
    payload: IngestRequest,
    db: Session = Depends(get_db),
) -> IngestResponse:
    return ingest(db, payload)
