"""SDK event callback. Never owns a request-scoped DB session."""

from __future__ import annotations

from lark_oapi.api.drive.v1.model.p2_drive_file_bitable_record_changed_v1 import (
    P2DriveFileBitableRecordChangedV1,
)

from app.core.logging import get_logger
from app.integrations.feishu.events.processor import FeishuEventProcessor

logger = get_logger(__name__)


def handle_bitable_record_changed(data: P2DriveFileBitableRecordChangedV1) -> None:
    try:
        FeishuEventProcessor().process_bitable_record_changed(data)
    except Exception:
        logger.exception("feishu inbound handler failed")
