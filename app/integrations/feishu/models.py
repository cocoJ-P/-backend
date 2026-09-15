"""ServiceCase ↔ Feishu Bitable binding. Integration metadata, not ServiceCase fields."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utc_now


class ServiceCaseFeishuBinding(Base):
    __tablename__ = "service_case_feishu_bindings"
    __table_args__ = (
        UniqueConstraint("service_case_id", name="uq_service_case_feishu_bindings_service_case_id"),
        UniqueConstraint(
            "bitable_app_token",
            "table_id",
            "record_id",
            name="uq_service_case_feishu_bindings_record",
        ),
        CheckConstraint(
            "sync_status IN ('pending', 'synced', 'failed')",
            name="ck_service_case_feishu_bindings_sync_status",
        ),
        CheckConstraint(
            "("
            "sync_status IN ('pending', 'failed')"
            ") OR ("
            "sync_status = 'synced' AND record_id IS NOT NULL AND last_synced_at IS NOT NULL"
            ")",
            name="ck_service_case_feishu_bindings_synced_record",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    service_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("service_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    bitable_app_token: Mapped[str] = mapped_column(String(128), nullable=False)
    table_id: Mapped[str] = mapped_column(String(128), nullable=False)
    record_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
