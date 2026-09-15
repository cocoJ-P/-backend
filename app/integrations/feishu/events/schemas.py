"""Normalized Feishu Bitable record-changed event. No SDK types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


BITABLE_RECORD_CHANGED_EVENT_TYPE = "drive.file.bitable_record_changed_v1"
SDK_BITABLE_RECORD_CHANGED_PROCESSOR_KEY = "p2.drive.file.bitable_record_changed_v1"

ACTION_RECORD_ADDED = "record_added"
ACTION_RECORD_DELETED = "record_deleted"
ACTION_RECORD_EDITED = "record_edited"


@dataclass(frozen=True)
class NormalizedBitableRecordChangedEvent:
    event_id: str
    event_type: str
    app_token: str | None
    table_id: str | None
    record_id: str | None
    action: str | None
    changed_field_ids: tuple[str, ...] = field(default_factory=tuple)
    occurred_at: datetime | None = None
    has_changed_field_ids: bool = False
