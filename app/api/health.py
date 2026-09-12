"""Health check endpoint."""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import check_connection, get_db
from app.core.logging import get_logger

router = APIRouter(tags=["Health"])
logger = get_logger(__name__)


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    database: str


@router.get("/health")
def health_check(
    response: Response,
    db: Session = Depends(get_db),
) -> HealthResponse:
    database_status = "ok"
    status = "ok"
    try:
        check_connection(db)
    except Exception:
        logger.exception("Database health check failed")
        database_status = "error"
        status = "error"
        response.status_code = 503

    return HealthResponse(
        status=status,
        service=settings.APP_NAME,
        environment=settings.APP_ENV,
        database=database_status,
    )
