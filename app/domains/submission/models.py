"""Persisted user-initiated check submissions. Business history, not a technical run."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utc_now


class UserSubmission(Base):
    __tablename__ = "user_submissions"
    __table_args__ = (
        CheckConstraint(
            "("
            "origin_type = 'user_input' AND origin_discovery_id IS NULL"
            ") OR ("
            "origin_type = 'discovery'"
            ")",
            name="ck_user_submissions_origin_consistency",
        ),
        UniqueConstraint(
            "enterprise_id",
            "user_id",
            "origin_discovery_id",
            name="uq_user_submissions_enterprise_user_origin_discovery",
        ),
        Index("ix_user_submissions_enterprise_created_at", "enterprise_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprises.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    input_type: Mapped[str] = mapped_column(String(16), nullable=False)
    input_content: Mapped[str] = mapped_column(Text, nullable=False)
    input_preview: Mapped[str] = mapped_column(String(512), nullable=False)
    origin_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="user_input",
        server_default="user_input",
    )
    origin_discovery_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("discovery_items.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    failure_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunity_sources.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    ingestion_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ingested_contents.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    intelligence_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("intelligence_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
