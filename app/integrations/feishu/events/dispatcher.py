"""Feishu event dispatcher. Registers ServiceCase inbound status sync."""

from __future__ import annotations

import lark_oapi as lark

from app.integrations.feishu.events.handler import handle_bitable_record_changed


def create_event_dispatcher() -> lark.EventDispatcherHandler:
    return (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_drive_file_bitable_record_changed_v1(handle_bitable_record_changed)
        .build()
    )
