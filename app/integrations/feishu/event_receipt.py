"""Feishu inbound event receipt. Integration idempotency, not a business domain."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utc_now


class FeishuEventReceipt(Base):
    __tablename__ = "feishu_event_receipts"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_feishu_event_receipts_event_id"),
        CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'failed')",
            name="ck_feishu_event_receipts_status",
        ),
        Index("ix_feishu_event_receipts_status", "status"),
        Index("ix_feishu_event_receipts_received_at", "received_at"),
        Index("ix_feishu_event_receipts_record_id", "record_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    app_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    table_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
