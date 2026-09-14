"""ServiceCase → Feishu field mapping tests. No HTTP. No DB."""

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError
from app.integrations.feishu.service_case_mapper import (
    FIELD_CASE_ID,
    FIELD_CREATED_AT,
    FIELD_CREATED_BY,
    FIELD_ENTERPRISE,
    FIELD_ORIGIN,
    FIELD_STATUS,
    FIELD_SUBMISSION_ID,
    FIELD_TITLE,
    ServiceCaseFeishuProjection,
    map_service_case_to_bitable_fields,
    to_bitable_datetime,
)

CASE_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SUBMISSION_ID = UUID("11111111-2222-3333-4444-555555555555")
CREATED_AT = datetime(2026, 9, 14, 12, 30, tzinfo=timezone.utc)


def _projection(**overrides) -> ServiceCaseFeishuProjection:
    values = {
        "title": "高新技术企业认定",
        "service_case_id": CASE_ID,
        "enterprise_name": "某某科技",
        "created_by_display_name": "张三",
        "origin_type": "user_input",
        "status": "open",
        "created_at": CREATED_AT,
        "submission_id": SUBMISSION_ID,
    }
    values.update(overrides)
    return ServiceCaseFeishuProjection(**values)


def test_mapper_emits_all_eight_fields():
    fields = map_service_case_to_bitable_fields(_projection())
    assert set(fields) == {
        FIELD_TITLE,
        FIELD_CASE_ID,
        FIELD_ENTERPRISE,
        FIELD_CREATED_BY,
        FIELD_ORIGIN,
        FIELD_STATUS,
        FIELD_CREATED_AT,
        FIELD_SUBMISSION_ID,
    }
    assert fields[FIELD_TITLE] == "高新技术企业认定"
    assert fields[FIELD_CASE_ID] == str(CASE_ID)
    assert fields[FIELD_ENTERPRISE] == "某某科技"
    assert fields[FIELD_CREATED_BY] == "张三"
    assert fields[FIELD_ORIGIN] == "用户提交"
    assert fields[FIELD_STATUS] == "待服务"
    assert fields[FIELD_CREATED_AT] == to_bitable_datetime(CREATED_AT)
    assert isinstance(fields[FIELD_CREATED_AT], int)
    assert fields[FIELD_SUBMISSION_ID] == str(SUBMISSION_ID)


def test_mapper_origin_labels():
    assert map_service_case_to_bitable_fields(_projection(origin_type="user_input"))[FIELD_ORIGIN] == "用户提交"
    assert map_service_case_to_bitable_fields(_projection(origin_type="discovery"))[FIELD_ORIGIN] == "来自发现"


def test_mapper_status_labels():
    assert map_service_case_to_bitable_fields(_projection(status="open"))[FIELD_STATUS] == "待服务"
    assert map_service_case_to_bitable_fields(_projection(status="in_progress"))[FIELD_STATUS] == "处理中"
    assert map_service_case_to_bitable_fields(_projection(status="completed"))[FIELD_STATUS] == "已完成"
    assert map_service_case_to_bitable_fields(_projection(status="closed"))[FIELD_STATUS] == "已关闭"


def test_mapper_datetime_uses_unix_milliseconds():
    assert to_bitable_datetime(CREATED_AT) == int(CREATED_AT.timestamp() * 1000)
    naive = datetime(2026, 9, 14, 12, 30)
    assert to_bitable_datetime(naive) == int(CREATED_AT.timestamp() * 1000)


def test_mapper_rejects_unknown_origin():
    with pytest.raises(FeishuIntegrationError) as exc:
        map_service_case_to_bitable_fields(_projection(origin_type="unknown"))
    assert exc.value.code == FeishuErrorCode.MAPPING_FAILED
