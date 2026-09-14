"""Persisted enterprise service matters created from UserSubmissions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utc_now


class ServiceCase(Base):
    __tablename__ = "service_cases"
    __table_args__ = (
        UniqueConstraint("submission_id", name="uq_service_cases_submission_id"),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'completed', 'closed')",
            name="ck_service_cases_status",
        ),
        CheckConstraint(
            "("
            "status IN ('open', 'in_progress') "
            "AND completed_at IS NULL AND closed_at IS NULL"
            ") OR ("
            "status = 'completed' AND completed_at IS NOT NULL AND closed_at IS NULL"
            ") OR ("
            "status = 'closed' AND closed_at IS NOT NULL AND completed_at IS NULL"
            ")",
            name="ck_service_cases_terminal_timestamps",
        ),
        Index("ix_service_cases_enterprise_created_at", "enterprise_id", "created_at"),
        Index(
            "ix_service_cases_enterprise_status_created_at",
            "enterprise_id",
            "status",
            "created_at",
        ),
        Index("ix_service_cases_created_by_user_created_at", "created_by_user_id", "created_at"),
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
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_submissions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
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
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
