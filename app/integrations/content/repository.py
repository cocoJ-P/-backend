"""Persistence helpers for ingested content."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.content.models import IngestedContent


def add_ingested_content(db: Session, record: IngestedContent) -> IngestedContent:
    db.add(record)
    db.flush()
    db.refresh(record)
    return record


def get_by_id(db: Session, ingestion_id: UUID) -> IngestedContent | None:
    return db.get(IngestedContent, ingestion_id)


def list_by_source(db: Session, source_id: UUID) -> list[IngestedContent]:
    statement = (
        select(IngestedContent)
        .where(IngestedContent.source_id == source_id)
        .order_by(IngestedContent.created_at.desc())
    )
    return list(db.scalars(statement).all())


def get_latest_by_source(db: Session, source_id: UUID) -> IngestedContent | None:
    records = list_by_source(db, source_id)
    return records[0] if records else None
