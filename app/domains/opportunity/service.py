"""Opportunity domain services."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.core.time import ensure_utc
from app.domains.opportunity import repository
from app.domains.opportunity.enums import OpportunityType
from app.domains.opportunity.models import (
    Opportunity,
    OpportunityRequirement,
    OpportunitySource,
)
from app.domains.opportunity.schemas import (
    OpportunityCreate,
    OpportunityRequirementCreate,
    OpportunitySourceCreate,
)


def list_opportunities(
    db: Session,
    opportunity_type: OpportunityType | None = None,
) -> list[Opportunity]:
    type_value = opportunity_type.value if opportunity_type is not None else None
    return repository.list_opportunities(db, opportunity_type=type_value)


def get_opportunity(db: Session, opportunity_id: UUID) -> Opportunity:
    opportunity = repository.get_opportunity(db, opportunity_id)
    if opportunity is None:
        raise NotFoundException(
            "Opportunity not found",
            code="OPPORTUNITY_NOT_FOUND",
        )
    return opportunity


def get_source(db: Session, source_id: UUID) -> OpportunitySource:
    source = repository.get_source(db, source_id)
    if source is None:
        raise NotFoundException(
            "Opportunity source not found",
            code="SOURCE_NOT_FOUND",
        )
    return source


def get_requirement(db: Session, requirement_id: UUID) -> OpportunityRequirement:
    requirement = repository.get_requirement(db, requirement_id)
    if requirement is None:
        raise NotFoundException(
            "Opportunity requirement not found",
            code="REQUIREMENT_NOT_FOUND",
        )
    return requirement


def create_opportunity(db: Session, payload: OpportunityCreate) -> Opportunity:
    opportunity = Opportunity(
        type=payload.type.value,
        title=payload.title.strip(),
        issuer=payload.issuer,
        region=payload.region,
        publish_date=payload.publish_date,
        deadline=payload.deadline,
        status=payload.status.value,
        official_url=payload.official_url,
        summary=payload.summary,
        resource_value=payload.resource_value,
        required_materials=payload.required_materials,
        application_process=payload.application_process,
    )
    repository.add_opportunity(db, opportunity)
    db.commit()
    return get_opportunity(db, opportunity.id)


def create_source(
    db: Session,
    payload: OpportunitySourceCreate,
    opportunity_id: UUID | None = None,
) -> OpportunitySource:
    mapped_opportunity_id = opportunity_id if opportunity_id is not None else payload.opportunity_id
    if mapped_opportunity_id is not None:
        get_opportunity(db, mapped_opportunity_id)

    published_at = payload.published_at
    if published_at is not None:
        published_at = ensure_utc(published_at)

    source = OpportunitySource(
        opportunity_id=mapped_opportunity_id,
        source_type=payload.source_type.value,
        title=payload.title.strip(),
        publisher=payload.publisher,
        url=payload.url,
        published_at=published_at,
        content_excerpt=payload.content_excerpt,
    )
    repository.add_source(db, source)
    db.commit()
    db.refresh(source)
    return source


def list_sources(db: Session, opportunity_id: UUID) -> list[OpportunitySource]:
    get_opportunity(db, opportunity_id)
    return repository.list_sources(db, opportunity_id)


def create_requirement(
    db: Session,
    opportunity_id: UUID,
    payload: OpportunityRequirementCreate,
) -> OpportunityRequirement:
    get_opportunity(db, opportunity_id)
    requirement = OpportunityRequirement(
        opportunity_id=opportunity_id,
        key=payload.key.strip(),
        label=payload.label.strip(),
        operator=payload.operator.value,
        expected_value=payload.expected_value,
        required=payload.required,
        description=payload.description,
        source_reference=payload.source_reference,
    )
    repository.add_requirement(db, requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


def list_requirements(db: Session, opportunity_id: UUID) -> list[OpportunityRequirement]:
    get_opportunity(db, opportunity_id)
    return repository.list_requirements(db, opportunity_id)
