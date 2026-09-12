"""Normalized opportunities, external sources, and eligibility requirements."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.core.time import utc_now


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    official_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    required_materials: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    application_process: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
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

    sources: Mapped[list[OpportunitySource]] = relationship(
        back_populates="opportunity",
        passive_deletes=True,
    )
    requirements: Mapped[list[OpportunityRequirement]] = relationship(
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )


class OpportunitySource(Base):
    __tablename__ = "opportunity_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    content_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    opportunity: Mapped[Opportunity | None] = relationship(back_populates="sources")
    intelligence_runs: Mapped[list["IntelligenceRun"]] = relationship(
        "IntelligenceRun",
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OpportunityRequirement(Base):
    __tablename__ = "opportunity_requirements"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_value: Mapped[object | None] = mapped_column(JSON, nullable=True)
    required: Mapped[bool] = mapped_column(default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="requirements")
