"""Pure ServiceCase → Feishu Bitable field mapping. No HTTP. No DB."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.time import ensure_utc
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError

FIELD_TITLE = "服务事项"
FIELD_CASE_ID = "Case ID"
FIELD_ENTERPRISE = "企业"
FIELD_CREATED_BY = "发起用户"
FIELD_ORIGIN = "来源"
FIELD_STATUS = "办理状态"
FIELD_CREATED_AT = "创建时间"
FIELD_SUBMISSION_ID = "Submission ID"

ORIGIN_LABELS = {
    "user_input": "用户提交",
    "discovery": "来自发现",
}

STATUS_LABELS = {
    "open": "待服务",
    "in_progress": "处理中",
    "completed": "已完成",
    "closed": "已关闭",
}

STATUS_FROM_LABELS = {label: status for status, label in STATUS_LABELS.items()}


@dataclass(frozen=True)
class ServiceCaseFeishuProjection:
    title: str
    service_case_id: UUID
    enterprise_name: str
    created_by_display_name: str
    origin_type: str
    status: str
    created_at: datetime
    submission_id: UUID


def to_bitable_datetime(value: datetime) -> int:
    """Bitable DateTime wire format: Unix timestamp in milliseconds."""
    return int(ensure_utc(value).timestamp() * 1000)


def case_id_equals_filter(service_case_id: UUID) -> dict[str, object]:
    return {
        "conjunction": "and",
        "conditions": [
            {
                "field_name": FIELD_CASE_ID,
                "operator": "is",
                "value": [str(service_case_id)],
            }
        ],
    }


def map_service_case_to_bitable_fields(projection: ServiceCaseFeishuProjection) -> dict[str, object]:
    origin = ORIGIN_LABELS.get(projection.origin_type)
    if origin is None:
        raise FeishuIntegrationError(
            FeishuErrorCode.MAPPING_FAILED,
            f"Unsupported submission origin_type: {projection.origin_type}",
            retryable=False,
        )
    status = STATUS_LABELS.get(projection.status)
    if status is None:
        raise FeishuIntegrationError(
            FeishuErrorCode.MAPPING_FAILED,
            f"Unsupported service case status: {projection.status}",
            retryable=False,
        )
    return {
        FIELD_TITLE: projection.title,
        FIELD_CASE_ID: str(projection.service_case_id),
        FIELD_ENTERPRISE: projection.enterprise_name,
        FIELD_CREATED_BY: projection.created_by_display_name,
        FIELD_ORIGIN: origin,
        FIELD_STATUS: status,
        FIELD_CREATED_AT: to_bitable_datetime(projection.created_at),
        FIELD_SUBMISSION_ID: str(projection.submission_id),
    }


def normalize_single_select_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        if not value:
            return None
        return normalize_single_select_value(value[0])
    if isinstance(value, dict):
        for key in ("text", "name", "value"):
            if key in value:
                return normalize_single_select_value(value.get(key))
        return None
    return None


def map_bitable_status_label_to_service_case(label: str) -> str:
    status = STATUS_FROM_LABELS.get((label or "").strip())
    if status is None:
        raise FeishuIntegrationError(
            FeishuErrorCode.UNSUPPORTED_SERVICE_CASE_STATUS,
            f"Unsupported Feishu service-case status: {label}",
            retryable=False,
        )
    return status


def read_remote_case_id(fields: dict) -> str | None:
    return normalize_single_select_value(fields.get(FIELD_CASE_ID))
