"""Persisted ingestion records. Content infrastructure, not Opportunity."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from app.core.time import utc_now


class IngestedContent(Base):
    __tablename__ = "ingested_contents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunity_sources.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    input_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    resolved_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetch_status: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(64), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
