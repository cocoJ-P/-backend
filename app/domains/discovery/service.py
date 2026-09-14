"""Discovery application service.

Creates enterprise-scoped DiscoveryItems from CurrentIdentity.
Does not send notifications, run matching, or analyze sources.
"""

from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.discovery.enums import (
    DiscoveryPriority,
    DiscoveryReferenceType,
    DiscoveryStatus,
)
from app.domains.discovery.models import DiscoveryItem
from app.domains.discovery.repository import (
    create_discovery,
    get_discovery_for_enterprise,
    list_discoveries_for_enterprise,
    withdraw_discovery as persist_withdraw,
)
from app.domains.discovery.schemas import (
    CreateDiscoveryRequest,
    CreateManualDiscoveryRequest,
    CreateOpportunityDiscoveryRequest,
    CreateSourceDiscoveryRequest,
    DiscoveryActor,
    DiscoveryItemDetail,
    DiscoveryItemListResponse,
    DiscoveryItemSummary,
)
from app.domains.identity.models import User
from app.domains.identity.repository import get_user_by_id
from app.domains.identity.schemas import CurrentIdentity
from app.domains.opportunity.enums import OpportunityType
from app.domains.opportunity.models import OpportunitySource
from app.domains.opportunity.repository import get_opportunity, get_source
from app.integrations.content.repository import get_latest_by_source

logger = get_logger(__name__)

SOURCE_TITLE_FALLBACK = "内容发现"
TITLE_MAX_LENGTH = 512
TEXT_MAX_LENGTH = 2000


def create_discovery_item(
    db: Session,
    identity: CurrentIdentity,
    payload: CreateDiscoveryRequest,
) -> DiscoveryItemDetail:
    snapshot = _build_snapshot(db, payload)
    now = utc_now()
    item = DiscoveryItem(
        enterprise_id=identity.enterprise_id,
        created_by_user_id=identity.user_id,
        status=DiscoveryStatus.ACTIVE.value,
        priority=payload.priority.value,
        reference_type=payload.reference_type,
        opportunity_id=snapshot["opportunity_id"],
        source_id=snapshot["source_id"],
        title=snapshot["title"],
        summary=snapshot["summary"],
        reason=_optional_text(getattr(payload, "reason", None)),
        opportunity_type=snapshot["opportunity_type"],
        issuer=snapshot["issuer"],
        region=snapshot["region"],
        deadline=snapshot["deadline"],
        reference_url=snapshot["reference_url"],
        created_at=now,
        updated_at=now,
        withdrawn_at=None,
    )
    create_discovery(db, item)
    logger.info(
        "discovery created discovery_id=%s enterprise_id=%s created_by_user_id=%s "
        "reference_type=%s opportunity_id=%s source_id=%s status=%s priority=%s",
        item.id,
        item.enterprise_id,
        item.created_by_user_id,
        item.reference_type,
        item.opportunity_id,
        item.source_id,
        item.status,
        item.priority,
    )
    return build_discovery_detail(db, item)


def list_discovery_items(
    db: Session,
    identity: CurrentIdentity,
    *,
    status: DiscoveryStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> DiscoveryItemListResponse:
    status_value = DiscoveryStatus.ACTIVE.value if status is None else status.value
    items = list_discoveries_for_enterprise(
        db,
        identity.enterprise_id,
        status=status_value,
        limit=limit,
        offset=offset,
    )
    users = _load_users(db, {item.created_by_user_id for item in items if item.created_by_user_id})
    return DiscoveryItemListResponse(
        items=[_to_summary(item, users.get(item.created_by_user_id)) for item in items],
        limit=limit,
        offset=offset,
    )


def get_discovery_item(
    db: Session,
    identity: CurrentIdentity,
    discovery_id: UUID,
) -> DiscoveryItemDetail:
    item = require_enterprise_discovery(db, identity.enterprise_id, discovery_id)
    return build_discovery_detail(db, item)


def withdraw_discovery_item(
    db: Session,
    identity: CurrentIdentity,
    discovery_id: UUID,
) -> DiscoveryItemDetail:
    item = require_enterprise_discovery(db, identity.enterprise_id, discovery_id)
    if item.status == DiscoveryStatus.WITHDRAWN.value:
        logger.info(
            "discovery withdraw idempotent discovery_id=%s enterprise_id=%s",
            item.id,
            item.enterprise_id,
        )
        return build_discovery_detail(db, item)
    persist_withdraw(db, item)
    logger.info(
        "discovery withdrawn discovery_id=%s enterprise_id=%s created_by_user_id=%s",
        item.id,
        item.enterprise_id,
        item.created_by_user_id,
    )
    return build_discovery_detail(db, item)


def build_discovery_detail(db: Session, item: DiscoveryItem) -> DiscoveryItemDetail:
    user = None
    if item.created_by_user_id is not None:
        user = get_user_by_id(db, item.created_by_user_id)
    summary = _to_summary(item, user)
    return DiscoveryItemDetail(
        **summary.model_dump(),
        updated_at=item.updated_at,
        withdrawn_at=item.withdrawn_at,
    )


def _build_snapshot(db: Session, payload: CreateDiscoveryRequest) -> dict:
    if isinstance(payload, CreateOpportunityDiscoveryRequest):
        return _snapshot_opportunity(db, payload)
    if isinstance(payload, CreateSourceDiscoveryRequest):
        return _snapshot_source(db, payload)
    if isinstance(payload, CreateManualDiscoveryRequest):
        return _snapshot_manual(payload)
    raise AppException(
        "INVALID_DISCOVERY_REFERENCE",
        "Unsupported discovery reference type",
        status_code=400,
    )


def _snapshot_opportunity(db: Session, payload: CreateOpportunityDiscoveryRequest) -> dict:
    opportunity = get_opportunity(db, payload.opportunity_id)
    if opportunity is None:
        raise NotFoundException("Opportunity not found", code="OPPORTUNITY_NOT_FOUND")
    return {
        "opportunity_id": opportunity.id,
        "source_id": None,
        "title": opportunity.title,
        "summary": opportunity.summary,
        "opportunity_type": opportunity.type,
        "issuer": opportunity.issuer,
        "region": opportunity.region,
        "deadline": opportunity.deadline,
        "reference_url": opportunity.official_url,
    }


def _snapshot_source(db: Session, payload: CreateSourceDiscoveryRequest) -> dict:
    source = get_source(db, payload.source_id)
    if source is None:
        raise NotFoundException("Opportunity source not found", code="SOURCE_NOT_FOUND")
    return {
        "opportunity_id": None,
        "source_id": source.id,
        "title": _source_display_title(db, source),
        "summary": source.content_excerpt,
        "opportunity_type": None,
        "issuer": source.publisher,
        "region": None,
        "deadline": None,
        "reference_url": source.url,
    }


def _snapshot_manual(payload: CreateManualDiscoveryRequest) -> dict:
    title = (payload.title or "").strip()
    if not title:
        raise AppException(
            "INVALID_DISCOVERY_INPUT",
            "Manual discovery title is required",
            status_code=400,
        )
    if len(title) > TITLE_MAX_LENGTH:
        raise AppException(
            "INVALID_DISCOVERY_INPUT",
            "Manual discovery title exceeds the length limit",
            status_code=400,
        )
    return {
        "opportunity_id": None,
        "source_id": None,
        "title": title,
        "summary": _optional_text(payload.summary),
        "opportunity_type": None,
        "issuer": None,
        "region": None,
        "deadline": None,
        "reference_url": None,
    }


def _source_display_title(db: Session, source: OpportunitySource) -> str:
    title = (source.title or "").strip()
    if title:
        return title
    ingestion = get_latest_by_source(db, source.id)
    ingested_title = (ingestion.raw_title or "").strip() if ingestion is not None else ""
    if ingested_title:
        return ingested_title
    host = urlparse(source.url or "").hostname
    if host:
        return host
    return SOURCE_TITLE_FALLBACK


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return text[:TEXT_MAX_LENGTH]


def require_enterprise_discovery(
    db: Session,
    enterprise_id: UUID,
    discovery_id: UUID,
) -> DiscoveryItem:
    item = get_discovery_for_enterprise(db, discovery_id, enterprise_id)
    if item is None:
        raise NotFoundException("Discovery not found", code="DISCOVERY_NOT_FOUND")
    return item


def _to_summary(item: DiscoveryItem, user: User | None) -> DiscoveryItemSummary:
    opportunity_type = None
    if item.opportunity_type:
        opportunity_type = OpportunityType(item.opportunity_type)
    created_by = None
    if user is not None:
        created_by = DiscoveryActor.model_validate(user)
    elif item.created_by_user_id is not None:
        created_by = DiscoveryActor(id=item.created_by_user_id, display_name="Unknown")
    return DiscoveryItemSummary(
        id=item.id,
        status=DiscoveryStatus(item.status),
        priority=DiscoveryPriority(item.priority),
        reference_type=DiscoveryReferenceType(item.reference_type),
        opportunity_id=item.opportunity_id,
        source_id=item.source_id,
        title=item.title,
        summary=item.summary,
        reason=item.reason,
        opportunity_type=opportunity_type,
        issuer=item.issuer,
        region=item.region,
        deadline=item.deadline,
        reference_url=item.reference_url,
        created_by=created_by,
        created_at=item.created_at,
    )


def _load_users(db: Session, user_ids: set[UUID]) -> dict[UUID, User]:
    if not user_ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(user_ids))).all()
    return {row.id: row for row in rows}
