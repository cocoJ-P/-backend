"""Persisted per-user state for a DiscoveryItem.

This is user-scoped interaction state. It is not DiscoveryItem.status
and it is not an interaction event log.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utc_now


class DiscoveryUserState(Base):
    __tablename__ = "discovery_user_states"
    __table_args__ = (
        UniqueConstraint("discovery_id", "user_id", name="uq_discovery_user_states_discovery_user"),
        CheckConstraint(
            "("
            "disposition IS NULL AND disposition_at IS NULL"
            ") OR ("
            "disposition IS NOT NULL AND disposition_at IS NOT NULL"
            ")",
            name="ck_discovery_user_states_disposition_timestamp",
        ),
        Index(
            "ix_discovery_user_states_enterprise_updated_at",
            "enterprise_id",
            "updated_at",
        ),
        Index(
            "ix_discovery_user_states_enterprise_disposition_updated_at",
            "enterprise_id",
            "disposition",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    discovery_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("discovery_items.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprises.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disposition: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    disposition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        index=True,
        nullable=False,
    )
