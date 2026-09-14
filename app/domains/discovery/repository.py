"""DiscoveryItem persistence. Routes must not query this table directly."""

from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domains.discovery.models import DiscoveryItem

PRIORITY_ORDER = case(
    (DiscoveryItem.priority == "high", 0),
    (DiscoveryItem.priority == "normal", 1),
    (DiscoveryItem.priority == "low", 2),
    else_=3,
)


def create_discovery(db: Session, item: DiscoveryItem) -> DiscoveryItem:
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_discovery_by_id(db: Session, discovery_id: UUID) -> DiscoveryItem | None:
    return db.get(DiscoveryItem, discovery_id)


def get_discovery_for_enterprise(
    db: Session,
    discovery_id: UUID,
    enterprise_id: UUID,
) -> DiscoveryItem | None:
    statement = select(DiscoveryItem).where(
        DiscoveryItem.id == discovery_id,
        DiscoveryItem.enterprise_id == enterprise_id,
    )
    return db.scalars(statement).first()


def list_discoveries_for_enterprise(
    db: Session,
    enterprise_id: UUID,
    *,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[DiscoveryItem]:
    statement = select(DiscoveryItem).where(DiscoveryItem.enterprise_id == enterprise_id)
    if status is not None:
        statement = statement.where(DiscoveryItem.status == status)
    statement = (
        statement.order_by(PRIORITY_ORDER, DiscoveryItem.created_at.desc(), DiscoveryItem.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def withdraw_discovery(db: Session, item: DiscoveryItem) -> DiscoveryItem:
    now = utc_now()
    item.status = "withdrawn"
    if item.withdrawn_at is None:
        item.withdrawn_at = now
    item.updated_at = now
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
