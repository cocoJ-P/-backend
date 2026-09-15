"""Feishu inbound status-sync tests. SDK Client is faked; no internet."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest
import requests
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.domains.service_case.enums import ServiceCaseStatus
from app.domains.service_case.models import ServiceCase
from app.domains.service_case.service import transition_service_case_status
from app.integrations.feishu.enums import FeishuErrorCode, FeishuEventReceiptStatus
from app.integrations.feishu.event_receipt import FeishuEventReceipt
from app.integrations.feishu.events.dispatcher import create_event_dispatcher
from app.integrations.feishu.events.parser import parse_bitable_record_changed_event
from app.integrations.feishu.events.processor import FeishuEventProcessor, UNMANAGED_RECORD_REASON
from app.integrations.feishu.events.schemas import (
    BITABLE_RECORD_CHANGED_EVENT_TYPE,
    SDK_BITABLE_RECORD_CHANGED_PROCESSOR_KEY,
)
from app.integrations.feishu.service import FeishuBindingService, create_feishu_integration
from app.integrations.feishu.service_case_mapper import FIELD_STATUS
from lark_oapi.api.drive.v1.model.p2_drive_file_bitable_record_changed_v1 import (
    P2DriveFileBitableRecordChangedV1,
)
from tests.feishu_sdk_fakes import FakeSdkRecord, FakeSdkResponse, make_fake_sdk
from tests.test_feishu_adapter import APP_SECRET, APP_TOKEN, TABLE_ID, TENANT_TOKEN, _enabled_config
from tests.test_feishu_binding import _insert_service_case

STATUS_FIELD_ID = "fldeZfJHTM"
RECORD_ID = "recINBOUND"


def _inbound_config(**overrides):
    return _enabled_config(service_case_status_field_id=STATUS_FIELD_ID, **overrides)


def _event_payload(
    *,
    event_id: str = "evt-1",
    file_token: str = APP_TOKEN,
    table_id: str = TABLE_ID,
    record_id: str = RECORD_ID,
    action: str = "record_edited",
    changed_fields: list[tuple[str, str]] | None = None,
    include_values: bool = True,
) -> dict:
    if changed_fields is None:
        changed_fields = [(STATUS_FIELD_ID, "处理中")]
    after_value = (
        [{"field_id": field_id, "field_value": value} for field_id, value in changed_fields]
        if include_values
        else None
    )
    action_body: dict = {"record_id": record_id, "action": action}
    if include_values:
        action_body["after_value"] = after_value
        action_body["before_value"] = []
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": BITABLE_RECORD_CHANGED_EVENT_TYPE,
            "create_time": "1710000000000",
            "token": "verification-token",
            "app_id": "cli_test_app",
            "tenant_key": "tenant",
        },
        "event": {
            "file_type": "bitable",
            "file_token": file_token,
            "table_id": table_id,
            "revision": 1,
            "action_list": [action_body],
            "update_time": 1710000000,
        },
    }


def _typed_event(**kwargs) -> P2DriveFileBitableRecordChangedV1:
    return P2DriveFileBitableRecordChangedV1(_event_payload(**kwargs))


def _count_receipts() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(FeishuEventReceipt)) or 0)
    finally:
        db.close()


def _get_receipt(event_id: str) -> FeishuEventReceipt | None:
    db = SessionLocal()
    try:
        row = db.scalars(
            select(FeishuEventReceipt).where(FeishuEventReceipt.event_id == event_id)
        ).first()
        if row is not None:
            db.expunge(row)
        return row
    finally:
        db.close()


def _get_case(case_id: UUID) -> ServiceCase:
    db = SessionLocal()
    try:
        row = db.get(ServiceCase, case_id)
        assert row is not None
        db.expunge(row)
        return row
    finally:
        db.close()


def _bind_synced(case_id: UUID, record_id: str = RECORD_ID):
    db = SessionLocal()
    try:
        binding = FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        FeishuBindingService().mark_synced(db, binding, record_id=record_id)
        return binding
    finally:
        db.close()


def _processor(remote_status: str = "处理中", handler=None, transition=None):
    def default_handler(operation, request):
        assert operation == "get"
        return FakeSdkResponse(record=FakeSdkRecord(RECORD_ID, {FIELD_STATUS: remote_status}))

    sdk, calls = make_fake_sdk(handler or default_handler)
    integration = create_feishu_integration(config=_inbound_config(), sdk_client=sdk)
    kwargs = {"integration": integration}
    if transition is not None:
        kwargs["transition"] = transition
    return FeishuEventProcessor(**kwargs), calls


def test_parser_normalizes_typed_sdk_event():
    event = _typed_event()
    parsed = parse_bitable_record_changed_event(event)
    assert len(parsed) == 1
    item = parsed[0]
    assert item.event_id == "evt-1"
    assert item.event_type == BITABLE_RECORD_CHANGED_EVENT_TYPE
    assert item.app_token == APP_TOKEN
    assert item.table_id == TABLE_ID
    assert item.record_id == RECORD_ID
    assert item.action == "record_edited"
    assert item.changed_field_ids == (STATUS_FIELD_ID,)
    assert item.has_changed_field_ids is True
    assert item.occurred_at is not None


def test_duplicate_event_is_not_processed_twice():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, calls = _processor()
    first = processor.process_bitable_record_changed(_typed_event())
    second = processor.process_bitable_record_changed(_typed_event())
    assert first is not None
    assert first.status == FeishuEventReceiptStatus.PROCESSED.value
    assert second is None
    assert _count_receipts() == 1
    assert len(calls) == 1
    assert _get_case(case_id).status == "in_progress"


def test_record_added_is_ignored():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, calls = _processor()
    receipt = processor.process_bitable_record_changed(_typed_event(action="record_added"))
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.IGNORED.value
    assert _get_case(case_id).status == "open"
    assert calls == []


def test_record_deleted_is_ignored():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, calls = _processor()
    receipt = processor.process_bitable_record_changed(_typed_event(action="record_deleted"))
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.IGNORED.value
    assert _get_case(case_id).status == "open"
    assert calls == []


def test_other_table_is_ignored():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, calls = _processor()
    receipt = processor.process_bitable_record_changed(_typed_event(table_id="tblOTHER"))
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.IGNORED.value
    assert _get_case(case_id).status == "open"
    assert calls == []


def test_other_field_edit_is_ignored():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, calls = _processor()
    receipt = processor.process_bitable_record_changed(
        _typed_event(changed_fields=[("fldk3psYxt", "某某科技")])
    )
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.IGNORED.value
    assert _get_case(case_id).status == "open"
    assert calls == []


def test_unmanaged_record_is_ignored():
    processor, calls = _processor()
    receipt = processor.process_bitable_record_changed(_typed_event())
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.IGNORED.value
    assert receipt.error_code == UNMANAGED_RECORD_REASON
    assert calls == []


def test_open_to_in_progress():
    case_id = _insert_service_case()
    binding = _bind_synced(case_id)
    processor, _calls = _processor("处理中")
    receipt = processor.process_bitable_record_changed(_typed_event())
    case = _get_case(case_id)
    assert case.status == "in_progress"
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.PROCESSED.value
    assert receipt.processed_at is not None
    db = SessionLocal()
    try:
        fresh = FeishuBindingService().get_by_service_case_id(db, case_id)
        assert fresh is not None
        assert fresh.sync_status == binding.sync_status
        assert fresh.last_synced_at == binding.last_synced_at
    finally:
        db.close()


def test_in_progress_to_completed_sets_completed_at():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    db = SessionLocal()
    try:
        case = db.get(ServiceCase, case_id)
        transition_service_case_status(db, case, ServiceCaseStatus.IN_PROGRESS)
    finally:
        db.close()
    processor, _calls = _processor("已完成")
    receipt = processor.process_bitable_record_changed(_typed_event())
    case = _get_case(case_id)
    assert case.status == "completed"
    assert case.completed_at is not None
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.PROCESSED.value


def test_open_to_closed_sets_closed_at():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, _calls = _processor("已关闭")
    receipt = processor.process_bitable_record_changed(_typed_event())
    case = _get_case(case_id)
    assert case.status == "closed"
    assert case.closed_at is not None
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.PROCESSED.value


def test_in_progress_to_closed():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    db = SessionLocal()
    try:
        transition_service_case_status(db, db.get(ServiceCase, case_id), ServiceCaseStatus.IN_PROGRESS)
    finally:
        db.close()
    processor, _calls = _processor("已关闭")
    receipt = processor.process_bitable_record_changed(_typed_event())
    case = _get_case(case_id)
    assert case.status == "closed"
    assert case.closed_at is not None
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.PROCESSED.value


def test_invalid_open_to_completed_fails_without_changing_case():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, _calls = _processor("已完成")
    receipt = processor.process_bitable_record_changed(_typed_event())
    case = _get_case(case_id)
    assert case.status == "open"
    assert case.completed_at is None
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.FAILED.value
    assert receipt.error_code == "INVALID_SERVICE_CASE_TRANSITION"


def test_terminal_completed_rejects_in_progress():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    db = SessionLocal()
    try:
        case = db.get(ServiceCase, case_id)
        transition_service_case_status(db, case, ServiceCaseStatus.IN_PROGRESS)
        transition_service_case_status(db, db.get(ServiceCase, case_id), ServiceCaseStatus.COMPLETED)
    finally:
        db.close()
    processor, _calls = _processor("处理中")
    receipt = processor.process_bitable_record_changed(_typed_event())
    assert _get_case(case_id).status == "completed"
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.FAILED.value
    assert receipt.error_code == "INVALID_SERVICE_CASE_TRANSITION"


def test_same_status_is_processed_without_transition():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    db = SessionLocal()
    try:
        transition_service_case_status(db, db.get(ServiceCase, case_id), ServiceCaseStatus.IN_PROGRESS)
    finally:
        db.close()
    calls = {"transition": 0}

    def spy(db, service_case, target):
        calls["transition"] += 1
        return transition_service_case_status(db, service_case, target)

    processor, _sdk_calls = _processor("处理中", transition=spy)
    receipt = processor.process_bitable_record_changed(_typed_event())
    assert _get_case(case_id).status == "in_progress"
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.PROCESSED.value
    assert calls["transition"] == 0


def test_unknown_remote_status_fails():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, _calls = _processor("暂停")
    receipt = processor.process_bitable_record_changed(_typed_event())
    assert _get_case(case_id).status == "open"
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.FAILED.value
    assert receipt.error_code == FeishuErrorCode.UNSUPPORTED_SERVICE_CASE_STATUS.value


def test_remote_fetch_timeout_fails_without_changing_case():
    case_id = _insert_service_case()
    _bind_synced(case_id)

    def handler(operation, request):
        raise requests.Timeout("timed out")

    processor, calls = _processor(handler=handler)
    receipt = processor.process_bitable_record_changed(_typed_event())
    assert _get_case(case_id).status == "open"
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.FAILED.value
    assert receipt.error_code == FeishuErrorCode.TIMEOUT.value
    assert len(calls) == 1


def test_get_record_does_not_hold_db_session():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    live: set = set()

    def factory():
        session = SessionLocal()
        live.add(id(session))
        original_close = session.close

        def close():
            live.discard(id(session))
            original_close()

        session.close = close  # type: ignore[method-assign]
        return session

    def handler(operation, request):
        assert live == set()
        return FakeSdkResponse(record=FakeSdkRecord(RECORD_ID, {FIELD_STATUS: "处理中"}))

    sdk, _calls = make_fake_sdk(handler)
    integration = create_feishu_integration(config=_inbound_config(), sdk_client=sdk)
    processor = FeishuEventProcessor(integration=integration, session_factory=factory)
    receipt = processor.process_bitable_record_changed(_typed_event())
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.PROCESSED.value
    assert _get_case(case_id).status == "in_progress"


def test_dispatcher_registers_typed_bitable_record_changed_event():
    handler = create_event_dispatcher()
    assert SDK_BITABLE_RECORD_CHANGED_PROCESSOR_KEY in handler._processorMap


def test_event_worker_disabled_does_not_connect(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("disabled worker must not construct WS client")

    monkeypatch.setattr("app.integrations.feishu.event_worker.create_feishu_ws_client", boom)
    from app.integrations.feishu.event_worker import main

    assert main() == 0


def test_event_worker_missing_status_field_id_fails_fast(monkeypatch, capsys):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEISHU_ENABLED", True)
    monkeypatch.setattr(settings, "FEISHU_APP_ID", "cli_test_app")
    monkeypatch.setattr(settings, "FEISHU_APP_SECRET", __import__("pydantic").SecretStr("secret"))
    monkeypatch.setattr(settings, "FEISHU_BITABLE_APP_TOKEN", APP_TOKEN)
    monkeypatch.setattr(settings, "FEISHU_SERVICE_CASE_TABLE_ID", TABLE_ID)
    monkeypatch.setattr(settings, "FEISHU_SERVICE_CASE_STATUS_FIELD_ID", "")

    def boom(*_args, **_kwargs):
        raise AssertionError("missing field id must not connect")

    monkeypatch.setattr("app.integrations.feishu.event_worker.create_feishu_ws_client", boom)
    from app.integrations.feishu.event_worker import main

    assert main() == 1
    assert "Feishu service-case status field id is not configured" in capsys.readouterr().out


def test_subscribe_cli_uses_drive_file_subscribe():
    seen = {}

    class FakeFileApi:
        def subscribe(self, request):
            seen["file_token"] = request.file_token
            seen["file_type"] = request.file_type
            seen["event_type"] = request.event_type
            seen["queries"] = list(request.queries)
            return SimpleNamespace(success=lambda: True, code=0, msg="ok", data=None)

    sdk = SimpleNamespace(drive=SimpleNamespace(v1=SimpleNamespace(file=FakeFileApi())))
    from app.integrations.feishu.subscribe_service_case_events import subscribe_service_case_events

    subscribe_service_case_events(config=_inbound_config(), sdk_client=sdk)
    assert seen["file_token"] == APP_TOKEN
    assert seen["file_type"] == "bitable"
    assert seen["event_type"] is None
    assert seen["queries"] == [("file_type", "bitable")]
    assert not any(key == "event_type" for key, _value in seen["queries"])


def test_single_select_shapes_are_normalized():
    case_id = _insert_service_case()
    _bind_synced(case_id)

    def handler(operation, request):
        return FakeSdkResponse(
            record=FakeSdkRecord(RECORD_ID, {FIELD_STATUS: {"name": "处理中"}})
        )

    processor, _calls = _processor(handler=handler)
    receipt = processor.process_bitable_record_changed(_typed_event())
    assert _get_case(case_id).status == "in_progress"
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.PROCESSED.value


@contextmanager
def _capture_events_log(caplog):
    logger = logging.getLogger("app.integrations.feishu.events")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level("INFO", logger="app.integrations.feishu.events"):
            yield
    finally:
        logger.removeHandler(caplog.handler)


def _assert_no_sensitive_log_content(text: str) -> None:
    assert "after_value" not in text
    assert "before_value" not in text
    assert "field_value" not in text
    assert "verification-token" not in text
    assert APP_SECRET not in text
    assert TENANT_TOKEN not in text
    assert "Authorization" not in text


def test_successful_transition_writes_safe_operational_logs(caplog):
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, _calls = _processor("处理中")
    with _capture_events_log(caplog):
        processor.process_bitable_record_changed(_typed_event())
    text = caplog.text
    assert "Feishu event received" in text
    assert "event_id=evt-1" in text
    assert f"record_id={RECORD_ID}" in text
    assert "action=record_edited" in text
    assert "ServiceCase status transition" in text
    assert f"case_id={case_id}" in text
    assert "from_status=open" in text
    assert "to_status=in_progress" in text
    assert "Feishu event processed" in text
    assert "receipt_status=processed" in text
    _assert_no_sensitive_log_content(text)


def test_invalid_transition_writes_error_code_log(caplog):
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, _calls = _processor("已完成")
    with _capture_events_log(caplog):
        processor.process_bitable_record_changed(_typed_event())
    text = caplog.text
    assert "Feishu event processing failed" in text
    assert "error_code=INVALID_SERVICE_CASE_TRANSITION" in text
    assert f"record_id={RECORD_ID}" in text
    assert f"case_id={case_id}" in text
    _assert_no_sensitive_log_content(text)


def test_failed_fetch_does_not_log_secrets_or_raw_payload(caplog):
    case_id = _insert_service_case()
    _bind_synced(case_id)

    def handler(operation, request):
        return FakeSdkResponse(
            code=1254301,
            msg=(
                f"Access denied Authorization: Bearer {TENANT_TOKEN} "
                f"app_secret={APP_SECRET} tenant_access_token={TENANT_TOKEN}"
            ),
        )

    processor, _calls = _processor(handler=handler)
    with _capture_events_log(caplog):
        processor.process_bitable_record_changed(_typed_event())
    text = caplog.text
    assert "Feishu event processing failed" in text
    assert "error_code=" in text
    _assert_no_sensitive_log_content(text)


def test_ignored_record_added_writes_reason_log(caplog):
    case_id = _insert_service_case()
    _bind_synced(case_id)
    processor, _calls = _processor()
    with _capture_events_log(caplog):
        processor.process_bitable_record_changed(_typed_event(action="record_added"))
    text = caplog.text
    assert "Feishu event received" in text
    assert "Feishu event ignored" in text
    assert "reason=record_added" in text
    assert "ServiceCase status transition" not in text
    _assert_no_sensitive_log_content(text)


def test_same_status_logs_already_current_not_transition(caplog):
    case_id = _insert_service_case()
    _bind_synced(case_id)
    db = SessionLocal()
    try:
        transition_service_case_status(db, db.get(ServiceCase, case_id), ServiceCaseStatus.IN_PROGRESS)
    finally:
        db.close()
    processor, _calls = _processor("处理中")
    with _capture_events_log(caplog):
        processor.process_bitable_record_changed(_typed_event())
    text = caplog.text
    assert "ServiceCase status already current" in text
    assert "status=in_progress" in text
    assert "ServiceCase status transition" not in text
    assert "Feishu event processed" in text
    _assert_no_sensitive_log_content(text)
