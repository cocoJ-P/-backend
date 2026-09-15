"""Parse official SDK bitable record-changed events into internal DTOs."""

from __future__ import annotations

from datetime import datetime, timezone

from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError
from app.integrations.feishu.events.schemas import (
    BITABLE_RECORD_CHANGED_EVENT_TYPE,
    NormalizedBitableRecordChangedEvent,
)


def parse_bitable_record_changed_event(data: object) -> list[NormalizedBitableRecordChangedEvent]:
    header = getattr(data, "header", None)
    event = getattr(data, "event", None)
    event_id = str(getattr(header, "event_id", None) or "").strip()
    if not event_id:
        raise FeishuIntegrationError(
            FeishuErrorCode.EVENT_PARSE_FAILED,
            "Feishu event did not include event_id",
            retryable=False,
        )
    event_type = str(
        getattr(header, "event_type", None) or BITABLE_RECORD_CHANGED_EVENT_TYPE
    ).strip()
    app_token = _optional_str(getattr(event, "file_token", None))
    table_id = _optional_str(getattr(event, "table_id", None))
    occurred_at = _occurred_at(getattr(event, "update_time", None), getattr(header, "create_time", None))
    actions = list(getattr(event, "action_list", None) or [])
    if not actions:
        return [
            NormalizedBitableRecordChangedEvent(
                event_id=event_id,
                event_type=event_type,
                app_token=app_token,
                table_id=table_id,
                record_id=None,
                action=None,
                changed_field_ids=(),
                occurred_at=occurred_at,
                has_changed_field_ids=False,
            )
        ]
    return [
        _parse_action(event_id, event_type, app_token, table_id, occurred_at, action)
        for action in actions
    ]


def _parse_action(
    event_id: str,
    event_type: str,
    app_token: str | None,
    table_id: str | None,
    occurred_at: datetime | None,
    action: object,
) -> NormalizedBitableRecordChangedEvent:
    field_ids, has_changed = _changed_field_ids(action)
    return NormalizedBitableRecordChangedEvent(
        event_id=event_id,
        event_type=event_type,
        app_token=app_token,
        table_id=table_id,
        record_id=_optional_str(getattr(action, "record_id", None)),
        action=_optional_str(getattr(action, "action", None)),
        changed_field_ids=field_ids,
        occurred_at=occurred_at,
        has_changed_field_ids=has_changed,
    )


def _changed_field_ids(action: object) -> tuple[tuple[str, ...], bool]:
    before = list(getattr(action, "before_value", None) or [])
    after = list(getattr(action, "after_value", None) or [])
    if not before and not after:
        return (), False
    ids: list[str] = []
    for item in before + after:
        field_id = _optional_str(getattr(item, "field_id", None))
        if field_id and field_id not in ids:
            ids.append(field_id)
    return tuple(ids), True


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _occurred_at(update_time: object, create_time: object) -> datetime | None:
    for raw in (update_time, create_time):
        parsed = _parse_timestamp(raw)
        if parsed is not None:
            return parsed
    return None


def _parse_timestamp(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number > 10_000_000_000:
        number = number / 1000
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
