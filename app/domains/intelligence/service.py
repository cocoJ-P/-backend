"""Intelligence API application service."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.domains.intelligence import repository as run_repository
from app.domains.intelligence.api_schemas import (
    IntelligenceAnalysisExecution,
    IntelligenceRunDetailResponse,
    IntelligenceRunResponse,
)
from app.domains.intelligence.orchestration import (
    OpportunityIntelligenceOrchestrator,
    load_intelligence_result,
)
from app.domains.opportunity.repository import get_source as get_opportunity_source
from app.integrations.llm.base import LLMProvider


def analyze_source(
    db: Session,
    source_id: UUID,
    *,
    ingestion_id: UUID | None = None,
    force: bool = False,
    provider: LLMProvider | None = None,
) -> IntelligenceAnalysisExecution:
    return OpportunityIntelligenceOrchestrator(db, provider=provider).analyze_source(
        source_id,
        ingestion_id=ingestion_id,
        force=force,
    )


def get_run(db: Session, run_id: UUID) -> IntelligenceRunDetailResponse:
    run = run_repository.get_run(db, run_id)
    if run is None:
        raise NotFoundException(
            "Intelligence run not found",
            code="INTELLIGENCE_RUN_NOT_FOUND",
        )
    result = None
    if run.intelligence_result_json:
        result = load_intelligence_result(run)
    return IntelligenceRunDetailResponse(
        run=IntelligenceRunResponse.model_validate(run),
        intelligence_result=result,
    )


def list_runs_for_source(
    db: Session,
    source_id: UUID,
    *,
    limit: int = 20,
) -> list[IntelligenceRunResponse]:
    source = get_opportunity_source(db, source_id)
    if source is None:
        raise NotFoundException(
            "Opportunity source not found",
            code="OPPORTUNITY_SOURCE_NOT_FOUND",
        )
    runs = run_repository.list_runs_for_source(db, source_id, limit=limit)
    return [IntelligenceRunResponse.model_validate(item) for item in runs]
