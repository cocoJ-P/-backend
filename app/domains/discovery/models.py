"""Persisted enterprise-scoped discovery items.

Snapshot fields record what was presented at create time. Deleting a
referenced Opportunity or Source must not erase this history.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utc_now


class DiscoveryItem(Base):
    __tablename__ = "discovery_items"
    __table_args__ = (
        CheckConstraint(
            "("
            "reference_type = 'manual' AND opportunity_id IS NULL AND source_id IS NULL"
            ") OR ("
            "reference_type = 'opportunity' AND source_id IS NULL"
            ") OR ("
            "reference_type = 'source' AND opportunity_id IS NULL"
            ")",
            name="ck_discovery_items_reference_consistency",
        ),
        Index(
            "ix_discovery_items_enterprise_status_created_at",
            "enterprise_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprises.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    reference_type: Mapped[str] = mapped_column(String(32), nullable=False)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunity_sources.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    opportunity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
