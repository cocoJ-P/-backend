"""Feishu D6.7 retry and reconciliation tests. SDK Client is faked; no internet."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import requests

from app.core.database import SessionLocal
from app.core.time import utc_now
from app.domains.service_case.enums import ServiceCaseStatus
from app.domains.service_case.models import ServiceCase
from app.domains.service_case.service import transition_service_case_status
from app.integrations.feishu.enums import (
    FeishuBindingSyncStatus,
    FeishuErrorCode,
    FeishuEventReceiptStatus,
)
from app.integrations.feishu.event_receipt import FeishuEventReceipt
from app.integrations.feishu.events.schemas import BITABLE_RECORD_CHANGED_EVENT_TYPE
from app.integrations.feishu.models import ServiceCaseFeishuBinding
from app.integrations.feishu.outbound import ServiceCaseFeishuSyncService
from app.integrations.feishu.recovery import FeishuSyncRecoveryService
from app.integrations.feishu.service import FeishuBindingService, create_feishu_integration
from app.integrations.feishu.service_case_mapper import FIELD_CASE_ID, FIELD_STATUS
from tests.feishu_sdk_fakes import FakeSdkRecord, FakeSdkResponse, make_fake_sdk
from tests.test_feishu_adapter import APP_TOKEN, TABLE_ID, _enabled_config
from tests.test_feishu_binding import _insert_service_case
from tests.test_feishu_inbound import (
    RECORD_ID,
    STATUS_FIELD_ID,
    _bind_synced,
    _get_case,
    _processor,
    _typed_event,
)
from tests.test_feishu_outbound import _create_count, _search_count


def _config():
    return _enabled_config(service_case_status_field_id=STATUS_FIELD_ID)


def _recovery(handler) -> tuple[FeishuSyncRecoveryService, list]:
    sdk, calls = make_fake_sdk(handler)
    integration = create_feishu_integration(config=_config(), sdk_client=sdk)
    return FeishuSyncRecoveryService(integration=integration), calls


def _op_count(calls, name: str) -> int:
    return sum(1 for operation, _request in calls if operation == name)


def _get_binding(case_id: UUID) -> ServiceCaseFeishuBinding:
    db = SessionLocal()
    try:
        binding = FeishuBindingService().get_by_service_case_id(db, case_id)
        assert binding is not None
        db.expunge(binding)
        return binding
    finally:
        db.close()


def _mark_failed(case_id: UUID, *, retryable: bool, record_id: str | None = None, code: str | None = None):
    db = SessionLocal()
    try:
        service = FeishuBindingService()
        binding = service.get_by_service_case_id(db, case_id)
        if binding is None:
            binding = service.create_pending_binding(
                db,
                service_case_id=case_id,
                bitable_app_token=APP_TOKEN,
                table_id=TABLE_ID,
            )
        if record_id:
            service.mark_synced(db, binding, record_id=record_id)
            binding = service.get_by_service_case_id(db, case_id)
            assert binding is not None
        service.mark_failed(
            db,
            binding,
            error_code=code or FeishuErrorCode.TIMEOUT.value,
            error_message="retry fixture",
            retryable=retryable,
        )
        return service.get_by_service_case_id(db, case_id)
    finally:
        db.close()


def _insert_receipt(
    *,
    status: str,
    record_id: str | None = RECORD_ID,
    retryable: bool = False,
    received_at=None,
    event_id: str | None = None,
) -> FeishuEventReceipt:
    db = SessionLocal()
    try:
        receipt = FeishuEventReceipt(
            event_id=event_id or f"evt-{uuid4()}",
            event_type=BITABLE_RECORD_CHANGED_EVENT_TYPE,
            app_token=APP_TOKEN,
            table_id=TABLE_ID,
            record_id=record_id,
            status=status,
            retryable=retryable,
            received_at=received_at or utc_now(),
        )
        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        db.expunge(receipt)
        return receipt
    finally:
        db.close()


def _search_create_handler(
    *,
    search_ids: list[str] | None = None,
    create_id: str = "recRETRY",
    case_id: UUID | None = None,
):
    search_ids = [] if search_ids is None else search_ids

    def handler(operation, request):
        if operation == "search":
            fields = {FIELD_CASE_ID: str(case_id)} if case_id is not None else {}
            if case_id is not None:
                fields[FIELD_STATUS] = "待服务"
            return FakeSdkResponse(
                items=[FakeSdkRecord(item, dict(fields)) for item in search_ids]
            )
        if operation == "create":
            fields = request.request_body.fields
            return FakeSdkResponse(record=FakeSdkRecord(create_id, fields))
        if operation == "get":
            return FakeSdkResponse(
                code=1254043,
                msg="record not found",
            )
        if operation == "update":
            fields = request.request_body.fields
            return FakeSdkResponse(record=FakeSdkRecord(request.record_id, fields))
        raise AssertionError(f"unexpected SDK operation {operation}")

    return handler


def test_outbound_retry_creates_when_remote_absent():
    case_id = _insert_service_case()
    _mark_failed(case_id, retryable=True)
    recovery, calls = _recovery(_search_create_handler(search_ids=[], create_id="recNEW"))
    result = recovery.retry_service_case_sync(case_id)
    binding = _get_binding(case_id)
    assert result.result == "synced"
    assert binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
    assert binding.record_id == "recNEW"
    assert binding.retry_count == 1
    assert binding.last_retry_at is not None
    assert binding.last_error_retryable is False
    assert _create_count(calls) == 1


def test_outbound_retry_adopts_existing_remote_without_create():
    case_id = _insert_service_case()
    _mark_failed(case_id, retryable=True)
    recovery, calls = _recovery(
        _search_create_handler(search_ids=["recEXIST"], create_id="recSHOULDNOT", case_id=case_id)
    )
    result = recovery.retry_service_case_sync(case_id)
    binding = _get_binding(case_id)
    assert result.result == "synced"
    assert binding.record_id == "recEXIST"
    assert _create_count(calls) == 0
    assert _search_count(calls) == 1


def test_outbound_retry_duplicate_remote_does_not_create():
    case_id = _insert_service_case()
    _mark_failed(case_id, retryable=True)
    recovery, calls = _recovery(_search_create_handler(search_ids=["recA", "recB"]))
    result = recovery.retry_service_case_sync(case_id)
    binding = _get_binding(case_id)
    assert result.result == "failed"
    assert result.error_code == FeishuErrorCode.DUPLICATE_CASE_RECORDS.value
    assert binding.sync_status == FeishuBindingSyncStatus.FAILED.value
    assert binding.last_error_retryable is False
    assert _create_count(calls) == 0


def test_reconcile_recreates_deleted_remote_record():
    case_id = _insert_service_case()
    _bind_synced(case_id, record_id="recOLD")
    recovery, calls = _recovery(_search_create_handler(search_ids=[], create_id="recR2"))
    result = recovery.reconcile_service_case(case_id)
    binding = _get_binding(case_id)
    assert result.result == "repaired"
    assert result.action == "recreated"
    assert binding.record_id == "recR2"
    assert binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
    assert _create_count(calls) == 1
    assert _get_case(case_id).status == "open"


def test_reconcile_adopts_replacement_and_does_not_create_third():
    case_id = _insert_service_case()
    _bind_synced(case_id, record_id="recOLD")
    recovery, calls = _recovery(
        _search_create_handler(search_ids=["recR2"], create_id="recR3", case_id=case_id)
    )
    result = recovery.reconcile_service_case(case_id)
    binding = _get_binding(case_id)
    assert result.action == "adopted"
    assert binding.record_id == "recR2"
    assert _create_count(calls) == 0


def test_binding_record_mismatch_does_not_write_remote():
    case_id = _insert_service_case()
    _mark_failed(case_id, retryable=True, record_id="recR1")
    other = str(uuid4())

    def handler(operation, request):
        if operation == "get":
            return FakeSdkResponse(
                record=FakeSdkRecord("recR1", {FIELD_CASE_ID: other, FIELD_STATUS: "待服务"})
            )
        raise AssertionError(f"must not {operation}")

    recovery, calls = _recovery(handler)
    result = recovery.retry_service_case_sync(case_id)
    assert result.result == "failed"
    assert result.error_code == FeishuErrorCode.BINDING_RECORD_MISMATCH.value
    assert _op_count(calls, "update") == 0
    assert _create_count(calls) == 0
    assert _search_count(calls) == 0


def test_retry_counter_increments_only_on_explicit_retry():
    case_id = _insert_service_case()
    db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
    finally:
        db.close()
    sdk, calls = make_fake_sdk(_search_create_handler(create_id="recFIRST"))
    integration = create_feishu_integration(config=_config(), sdk_client=sdk)
    first = ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
    assert first is not None
    assert first.retry_count == 0
    assert first.last_retry_at is None
    _mark_failed(case_id, retryable=True)
    recovery, _retry_calls = _recovery(_search_create_handler(create_id="recSECOND"))
    result = recovery.retry_service_case_sync(case_id)
    assert result.retry_count == 1
    assert _get_binding(case_id).last_retry_at is not None
    assert _create_count(calls) == 1


def test_retryability_flags_on_binding_and_receipt():
    case_id = _insert_service_case()
    db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
    finally:
        db.close()

    def timeout_handler(operation, request):
        if operation == "search":
            raise requests.Timeout("timed out")
        raise AssertionError(operation)

    sdk, _calls = make_fake_sdk(timeout_handler)
    integration = create_feishu_integration(config=_config(), sdk_client=sdk)
    ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
    assert _get_binding(case_id).last_error_retryable is True
    assert _get_binding(case_id).last_error_code == FeishuErrorCode.TIMEOUT.value

    def network_handler(operation, request):
        if operation == "search":
            raise requests.ConnectionError("down")
        raise AssertionError(operation)

    case_id_n = _insert_service_case()
    db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id_n,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
    finally:
        db.close()
    sdk, _calls = make_fake_sdk(network_handler)
    integration = create_feishu_integration(config=_config(), sdk_client=sdk)
    ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id_n)
    assert _get_binding(case_id_n).last_error_retryable is True

    def rate_handler(operation, request):
        if operation == "search":
            return FakeSdkResponse(code=99991400, msg="rate limited")
        raise AssertionError(operation)

    case_id_r = _insert_service_case()
    db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id_r,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
    finally:
        db.close()
    sdk, _calls = make_fake_sdk(rate_handler)
    integration = create_feishu_integration(config=_config(), sdk_client=sdk)
    ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id_r)
    assert _get_binding(case_id_r).last_error_retryable is True

    case_id_i = _insert_service_case()
    _bind_synced(case_id_i, record_id="recINV")
    processor, _calls = _processor(handler=lambda operation, request: FakeSdkResponse(
        record=FakeSdkRecord("recINV", {FIELD_STATUS: "已完成"})
    ))
    receipt = processor.process_bitable_record_changed(
        _typed_event(event_id="evt-invalid", record_id="recINV")
    )
    assert receipt is not None
    assert receipt.retryable is False
    assert receipt.error_code == "INVALID_SERVICE_CASE_TRANSITION"

    case_id_u = _insert_service_case()
    _bind_synced(case_id_u, record_id="recUNSUP")
    processor, _calls = _processor(handler=lambda operation, request: FakeSdkResponse(
        record=FakeSdkRecord("recUNSUP", {FIELD_STATUS: "暂停"})
    ))
    receipt = processor.process_bitable_record_changed(
        _typed_event(event_id="evt-unsupported", record_id="recUNSUP")
    )
    assert receipt is not None
    assert receipt.retryable is False
    assert receipt.error_code == FeishuErrorCode.UNSUPPORTED_SERVICE_CASE_STATUS.value


def test_inbound_failed_retry_applies_valid_transition():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    state = {"fail": True}

    def handler(operation, request):
        assert operation == "get"
        if state["fail"]:
            raise requests.Timeout("timed out")
        return FakeSdkResponse(record=FakeSdkRecord(RECORD_ID, {FIELD_STATUS: "处理中"}))

    processor, _calls = _processor(handler=handler)
    receipt = processor.process_bitable_record_changed(_typed_event(event_id="evt-retry"))
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.FAILED.value
    assert receipt.retryable is True
    assert _get_case(case_id).status == "open"
    state["fail"] = False
    result = FeishuSyncRecoveryService(
        integration=processor._integration
    ).retry_event_receipt(receipt.id)
    assert result.result == "processed"
    assert result.retry_count == 1
    assert _get_case(case_id).status == "in_progress"
    db = SessionLocal()
    try:
        fresh = db.get(FeishuEventReceipt, receipt.id)
        assert fresh is not None
        assert fresh.status == FeishuEventReceiptStatus.PROCESSED.value
        assert fresh.retry_count == 1
        assert fresh.last_retry_at is not None
    finally:
        db.close()


def test_batch_recovers_stale_received():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    receipt = _insert_receipt(
        status=FeishuEventReceiptStatus.RECEIVED.value,
        received_at=utc_now() - timedelta(seconds=400),
    )

    def handler(operation, request):
        assert operation == "get"
        return FakeSdkResponse(record=FakeSdkRecord(RECORD_ID, {FIELD_STATUS: "处理中"}))

    recovery, _calls = _recovery(handler)
    summary = recovery.retry_failed_syncs(direction="inbound", limit=20)
    assert summary.attempted == 1
    assert summary.succeeded == 1
    assert _get_case(case_id).status == "in_progress"
    db = SessionLocal()
    try:
        fresh = db.get(FeishuEventReceipt, receipt.id)
        assert fresh is not None
        assert fresh.status == FeishuEventReceiptStatus.PROCESSED.value
    finally:
        db.close()


def test_batch_skips_processed_ignored_and_nonretryable():
    _insert_receipt(status=FeishuEventReceiptStatus.PROCESSED.value, event_id="evt-p")
    _insert_receipt(status=FeishuEventReceiptStatus.IGNORED.value, event_id="evt-i")
    _insert_receipt(
        status=FeishuEventReceiptStatus.FAILED.value,
        retryable=False,
        event_id="evt-nr",
    )
    case_id = _insert_service_case()
    _mark_failed(case_id, retryable=False, code=FeishuErrorCode.DUPLICATE_CASE_RECORDS.value)
    recovery, _calls = _recovery(_search_create_handler())
    summary = recovery.retry_failed_syncs(direction="all", limit=20)
    assert summary.attempted == 0
    assert summary.succeeded == 0


def test_batch_limit_and_continues_after_failure():
    ids = [_insert_service_case() for _ in range(5)]
    for case_id in ids:
        _mark_failed(case_id, retryable=True)
    seen = {"count": 0}

    def handler(operation, request):
        if operation == "search":
            return FakeSdkResponse(items=[])
        if operation == "create":
            seen["count"] += 1
            if seen["count"] == 2:
                return FakeSdkResponse(code=1, msg="boom")
            return FakeSdkResponse(record=FakeSdkRecord(f"rec{seen['count']}", {}))
        raise AssertionError(operation)

    recovery, _calls = _recovery(handler)
    summary = recovery.retry_failed_syncs(direction="outbound", limit=3)
    assert summary.attempted == 3
    assert summary.succeeded == 2
    assert summary.failed == 1


def test_batch_limit_caps_candidates():
    for _ in range(8):
        case_id = _insert_service_case()
        _mark_failed(case_id, retryable=True)

    def handler(operation, request):
        if operation == "search":
            return FakeSdkResponse(items=[])
        if operation == "create":
            return FakeSdkResponse(record=FakeSdkRecord("recX", {}))
        raise AssertionError(operation)

    recovery, calls = _recovery(handler)
    summary = recovery.retry_failed_syncs(direction="outbound", limit=3)
    assert summary.attempted == 3
    assert _create_count(calls) == 3


def test_status_drift_repair_does_not_change_backend():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    db = SessionLocal()
    try:
        transition_service_case_status(
            db, db.get(ServiceCase, case_id), ServiceCaseStatus.IN_PROGRESS
        )
    finally:
        db.close()

    def handler(operation, request):
        if operation == "get":
            return FakeSdkResponse(
                record=FakeSdkRecord(
                    RECORD_ID,
                    {FIELD_CASE_ID: str(case_id), FIELD_STATUS: "待服务"},
                )
            )
        if operation == "update":
            fields = request.request_body.fields
            assert fields == {FIELD_STATUS: "处理中"}
            return FakeSdkResponse(record=FakeSdkRecord(RECORD_ID, fields))
        raise AssertionError(operation)

    recovery, calls = _recovery(handler)
    result = recovery.reconcile_service_case(case_id)
    assert result.action == "status_drift_repaired"
    assert result.remote_status == "处理中"
    assert _get_case(case_id).status == "in_progress"
    assert _op_count(calls, "update") == 1
    assert _create_count(calls) == 0


def test_terminal_drift_repairs_remote_not_backend():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    db = SessionLocal()
    try:
        case = db.get(ServiceCase, case_id)
        transition_service_case_status(db, case, ServiceCaseStatus.IN_PROGRESS)
        transition_service_case_status(
            db, db.get(ServiceCase, case_id), ServiceCaseStatus.COMPLETED
        )
    finally:
        db.close()

    def handler(operation, request):
        if operation == "get":
            return FakeSdkResponse(
                record=FakeSdkRecord(
                    RECORD_ID,
                    {FIELD_CASE_ID: str(case_id), FIELD_STATUS: "处理中"},
                )
            )
        if operation == "update":
            assert request.request_body.fields == {FIELD_STATUS: "已完成"}
            return FakeSdkResponse(
                record=FakeSdkRecord(RECORD_ID, request.request_body.fields)
            )
        raise AssertionError(operation)

    recovery, _calls = _recovery(handler)
    result = recovery.reconcile_service_case(case_id)
    assert result.action == "status_drift_repaired"
    assert _get_case(case_id).status == "completed"


def test_same_status_reconcile_skips_update():
    case_id = _insert_service_case()
    _bind_synced(case_id)

    def handler(operation, request):
        if operation == "get":
            return FakeSdkResponse(
                record=FakeSdkRecord(
                    RECORD_ID,
                    {FIELD_CASE_ID: str(case_id), FIELD_STATUS: "待服务"},
                )
            )
        raise AssertionError(f"must not {operation}")

    recovery, calls = _recovery(handler)
    result = recovery.reconcile_service_case(case_id)
    assert result.result == "already_consistent"
    assert _op_count(calls, "update") == 0
    assert _get_case(case_id).status == "open"


def test_reconcile_inbound_same_status_is_noop():
    case_id = _insert_service_case()
    _bind_synced(case_id)
    db = SessionLocal()
    try:
        transition_service_case_status(
            db, db.get(ServiceCase, case_id), ServiceCaseStatus.IN_PROGRESS
        )
    finally:
        db.close()

    def handler(operation, request):
        if operation == "get":
            return FakeSdkResponse(
                record=FakeSdkRecord(
                    RECORD_ID,
                    {FIELD_CASE_ID: str(case_id), FIELD_STATUS: "待服务"},
                )
            )
        if operation == "update":
            return FakeSdkResponse(
                record=FakeSdkRecord(RECORD_ID, {FIELD_STATUS: "处理中"})
            )
        raise AssertionError(operation)

    recovery, _calls = _recovery(handler)
    recovery.reconcile_service_case(case_id)
    processor, _pc = _processor("处理中")
    receipt = processor.process_bitable_record_changed(_typed_event(event_id="evt-loop"))
    assert receipt is not None
    assert receipt.status == FeishuEventReceiptStatus.PROCESSED.value
    assert _get_case(case_id).status == "in_progress"


def test_retry_remote_calls_do_not_hold_db_session():
    case_id = _insert_service_case()
    _mark_failed(case_id, retryable=True)
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
        if operation == "search":
            return FakeSdkResponse(items=[])
        if operation == "create":
            return FakeSdkResponse(record=FakeSdkRecord("recTXN", {}))
        raise AssertionError(operation)

    sdk, _calls = make_fake_sdk(handler)
    integration = create_feishu_integration(config=_config(), sdk_client=sdk)
    recovery = FeishuSyncRecoveryService(integration=integration, session_factory=factory)
    result = recovery.retry_service_case_sync(case_id)
    assert result.result == "synced"


def test_synced_retry_is_already_synced_without_remote_write():
    case_id = _insert_service_case()
    _bind_synced(case_id)

    def handler(operation, request):
        raise AssertionError(f"must not {operation}")

    recovery, _calls = _recovery(handler)
    result = recovery.retry_service_case_sync(case_id)
    assert result.result == "already_synced"
    assert result.retry_count == 0


def test_batch_zero_candidates_prints_summary(capsys):
    from app.integrations.feishu.retry_failed_syncs import main as batch_main

    code = batch_main(["--direction", "all", "--limit", "20"])
    assert code == 0
    output = capsys.readouterr().out
    assert "Attempted: 0" in output
    assert "Succeeded: 0" in output
    assert "Failed: 0" in output
    assert "Skipped: 0" in output
