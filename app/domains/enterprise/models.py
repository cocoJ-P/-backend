"""Enterprise identity and growth-state snapshots."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.core.time import utc_now


class Enterprise(Base):
    __tablename__ = "enterprises"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    established_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    enterprise_type: Mapped[str] = mapped_column(String(64), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    states: Mapped[list[EnterpriseState]] = relationship(
        back_populates="enterprise",
        cascade="all, delete-orphan",
    )


class EnterpriseState(Base):
    __tablename__ = "enterprise_states"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprises.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    product_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    business_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    team_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    funding_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualifications: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    current_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_constraint: Mapped[str | None] = mapped_column(Text, nullable=True)
    recent_events: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    available_materials: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    enterprise: Mapped[Enterprise] = relationship(back_populates="states")
