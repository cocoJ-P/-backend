"""Database access for IntelligenceRun records."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.intelligence.enums import IntelligenceRunStatus
from app.domains.intelligence.models import IntelligenceRun


def create_run(db: Session, run: IntelligenceRun) -> IntelligenceRun:
    db.add(run)
    db.flush()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: UUID) -> IntelligenceRun | None:
    return db.get(IntelligenceRun, run_id)


def list_runs_for_source(
    db: Session,
    source_id: UUID,
    *,
    limit: int = 20,
) -> list[IntelligenceRun]:
    statement = (
        select(IntelligenceRun)
        .where(IntelligenceRun.source_id == source_id)
        .order_by(IntelligenceRun.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def find_latest_succeeded_by_fingerprint(
    db: Session,
    *,
    source_id: UUID,
    analysis_fingerprint: str,
) -> IntelligenceRun | None:
    statement = (
        select(IntelligenceRun)
        .where(IntelligenceRun.source_id == source_id)
        .where(IntelligenceRun.analysis_fingerprint == analysis_fingerprint)
        .where(IntelligenceRun.status == IntelligenceRunStatus.SUCCEEDED.value)
        .order_by(IntelligenceRun.created_at.desc())
        .limit(1)
    )
    return db.scalars(statement).first()


def mark_succeeded(
    db: Session,
    run: IntelligenceRun,
    *,
    rule_result_json: dict,
    intelligence_result_json: dict,
    usage_json: dict,
    provider: str,
    model: str,
    completed_at,
) -> IntelligenceRun:
    run.status = IntelligenceRunStatus.SUCCEEDED.value
    run.rule_result_json = rule_result_json
    run.intelligence_result_json = intelligence_result_json
    run.usage_json = usage_json
    run.provider = provider
    run.model = model
    run.error_code = None
    run.error_message = None
    run.completed_at = completed_at
    db.add(run)
    db.flush()
    db.refresh(run)
    return run


def mark_failed(
    db: Session,
    run: IntelligenceRun,
    *,
    error_code: str,
    error_message: str | None,
    completed_at,
    rule_result_json: dict | None = None,
) -> IntelligenceRun:
    run.status = IntelligenceRunStatus.FAILED.value
    run.error_code = error_code
    run.error_message = error_message
    run.completed_at = completed_at
    if rule_result_json is not None:
        run.rule_result_json = rule_result_json
    db.add(run)
    db.flush()
    db.refresh(run)
    return run
