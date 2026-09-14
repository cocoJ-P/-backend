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
