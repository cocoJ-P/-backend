"""Lightweight Feishu DTO objects. No ServiceCase field mapping."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FeishuBitableRecord(BaseModel):
    record_id: str
    fields: dict[str, Any] = Field(default_factory=dict)
