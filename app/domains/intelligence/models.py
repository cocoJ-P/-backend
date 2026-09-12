"""Persisted Intelligence analysis runs.

A succeeded run means the pipeline finished. It does not mean the claimed
opportunity has been externally verified.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.core.time import utc_now
from app.domains.opportunity.models import OpportunitySource
from app.integrations.content.models import IngestedContent


class IntelligenceRun(Base):
    __tablename__ = "intelligence_runs"

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
    ingestion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ingested_contents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    intelligence_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    usage_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )

    source: Mapped[OpportunitySource] = relationship(back_populates="intelligence_runs")
    ingestion: Mapped[IngestedContent] = relationship()
