"""Opportunity database access."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domains.opportunity.models import (
    Opportunity,
    OpportunityRequirement,
    OpportunitySource,
)


def list_opportunities(db: Session, opportunity_type: str | None = None) -> list[Opportunity]:
    statement = select(Opportunity)
    if opportunity_type is not None:
        statement = statement.where(Opportunity.type == opportunity_type)
    statement = statement.order_by(Opportunity.created_at.asc(), Opportunity.title.asc())
    return list(db.scalars(statement).all())


def get_opportunity(db: Session, opportunity_id: UUID) -> Opportunity | None:
    statement = (
        select(Opportunity)
        .options(
            selectinload(Opportunity.sources),
            selectinload(Opportunity.requirements),
        )
        .where(Opportunity.id == opportunity_id)
    )
    return db.scalars(statement).first()


def add_opportunity(db: Session, opportunity: Opportunity) -> Opportunity:
    db.add(opportunity)
    db.flush()
    db.refresh(opportunity)
    return opportunity


def get_source(db: Session, source_id: UUID) -> OpportunitySource | None:
    return db.get(OpportunitySource, source_id)


def list_sources(db: Session, opportunity_id: UUID) -> list[OpportunitySource]:
    statement = (
        select(OpportunitySource)
        .where(OpportunitySource.opportunity_id == opportunity_id)
        .order_by(OpportunitySource.created_at.asc())
    )
    return list(db.scalars(statement).all())


def add_source(db: Session, source: OpportunitySource) -> OpportunitySource:
    db.add(source)
    db.flush()
    db.refresh(source)
    return source


def get_requirement(db: Session, requirement_id: UUID) -> OpportunityRequirement | None:
    return db.get(OpportunityRequirement, requirement_id)


def list_requirements(db: Session, opportunity_id: UUID) -> list[OpportunityRequirement]:
    statement = (
        select(OpportunityRequirement)
        .where(OpportunityRequirement.opportunity_id == opportunity_id)
        .order_by(OpportunityRequirement.created_at.asc())
    )
    return list(db.scalars(statement).all())


def add_requirement(
    db: Session,
    requirement: OpportunityRequirement,
) -> OpportunityRequirement:
    db.add(requirement)
    db.flush()
    db.refresh(requirement)
    return requirement
