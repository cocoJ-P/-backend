"""Opportunity Intelligence HTTP API."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.intelligence import service
from app.domains.intelligence.api_schemas import (
    AnalyzeRequest,
    IntelligenceAnalyzeResponse,
    IntelligenceRunDetailResponse,
    IntelligenceRunResponse,
)

router = APIRouter(tags=["Opportunity Intelligence"])


@router.post(
    "/opportunity-sources/{source_id}/analyze",
    response_model=IntelligenceAnalyzeResponse,
)
def analyze_opportunity_source(
    source_id: UUID,
    payload: AnalyzeRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> IntelligenceAnalyzeResponse:
    request = payload or AnalyzeRequest()
    execution = service.analyze_source(
        db,
        source_id,
        ingestion_id=request.ingestion_id,
        force=request.force,
    )
    return IntelligenceAnalyzeResponse(
        run=execution.run,
        reused=execution.reused,
        intelligence_result=execution.intelligence_result,
    )


@router.get(
    "/intelligence-runs/{run_id}",
    response_model=IntelligenceRunDetailResponse,
)
def get_intelligence_run(
    run_id: UUID,
    db: Session = Depends(get_db),
) -> IntelligenceRunDetailResponse:
    return service.get_run(db, run_id)


@router.get(
    "/opportunity-sources/{source_id}/intelligence-runs",
    response_model=list[IntelligenceRunResponse],
)
def list_source_intelligence_runs(
    source_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[IntelligenceRunResponse]:
    return service.list_runs_for_source(db, source_id, limit=limit)
