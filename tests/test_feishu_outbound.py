"""ServiceCase → Feishu outbound sync tests. All HTTP is mocked."""

from __future__ import annotations

import json
from uuid import UUID

import httpx
from fastapi import BackgroundTasks
from pydantic import SecretStr

from app.core.config import settings
from app.core.database import SessionLocal
from app.domains.service_case.models import ServiceCase
from app.integrations.feishu.enums import FeishuBindingSyncStatus, FeishuErrorCode
from app.integrations.feishu.models import ServiceCaseFeishuBinding
from app.integrations.feishu.outbound import (
    ServiceCaseFeishuSyncService,
    run_service_case_feishu_sync,
)
from app.integrations.feishu.repository import save_binding
from app.integrations.feishu.service import FeishuBindingService, create_feishu_integration
from app.integrations.feishu.service_case_mapper import FIELD_CASE_ID, FIELD_CREATED_AT
from app.integrations.feishu.sync_service_case import main as sync_cli_main
from app.integrations.feishu.token_provider import TOKEN_PATH
from tests.test_feishu_adapter import APP_SECRET, APP_TOKEN, TABLE_ID, TENANT_TOKEN, _enabled_config
from tests.test_feishu_binding import _count_bindings, _insert_service_case
from tests.test_service_cases import _create_succeeded_submission, _header


def _token_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "ok",
            "tenant_access_token": TENANT_TOKEN,
            "expire": 7200,
        },
    )


def _record_response(record_id: str, fields: dict | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {"record": {"record_id": record_id, "fields": fields or {}}},
        },
    )


def _search_response(record_ids: list[str]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "success",
            "data": {
                "items": [{"record_id": item, "fields": {FIELD_CASE_ID: "x"}} for item in record_ids]
            },
        },
    )


def _mock_integration(handler):
    requests: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    http_client = httpx.Client(
        transport=httpx.MockTransport(wrapped),
        base_url="https://open.feishu.cn",
        timeout=10,
    )
    integration = create_feishu_integration(config=_enabled_config(), http_client=http_client)
    return integration, requests, http_client


def _enable_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "FEISHU_ENABLED", True)
    monkeypatch.setattr(settings, "FEISHU_APP_ID", "cli_test_app")
    monkeypatch.setattr(settings, "FEISHU_APP_SECRET", SecretStr(APP_SECRET))
    monkeypatch.setattr(settings, "FEISHU_BITABLE_APP_TOKEN", APP_TOKEN)
    monkeypatch.setattr(settings, "FEISHU_SERVICE_CASE_TABLE_ID", TABLE_ID)


def _patch_integration(monkeypatch, integration) -> None:
    _enable_settings(monkeypatch)
    monkeypatch.setattr(
        "app.integrations.feishu.outbound.create_feishu_integration",
        lambda **_kwargs: integration,
    )


def _capture_background(monkeypatch) -> list[tuple]:
    queued: list[tuple] = []

    def capture(self, func, *args, **kwargs):
        queued.append((func, args, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", capture)
    return queued


def _get_binding(service_case_id: UUID) -> ServiceCaseFeishuBinding | None:
    db = SessionLocal()
    try:
        return FeishuBindingService().get_by_service_case_id(db, service_case_id)
    finally:
        db.close()


def _get_case(service_case_id: UUID) -> ServiceCase:
    db = SessionLocal()
    try:
        row = db.get(ServiceCase, service_case_id)
        assert row is not None
        db.expunge(row)
        return row
    finally:
        db.close()


def _is_create(request: httpx.Request) -> bool:
    return request.method == "POST" and request.url.path.endswith("/records")


def _is_search(request: httpx.Request) -> bool:
    return request.method == "POST" and request.url.path.endswith("/records/search")


def _create_then_search_handler(*, search_ids: list[str] | None = None, create_id: str = "rec123"):
    search_ids = [] if search_ids is None else search_ids

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return _token_response()
        if _is_search(request):
            return _search_response(search_ids)
        if _is_create(request):
            body = json.loads(request.content)
            assert FIELD_CASE_ID in body["fields"]
            assert FIELD_CREATED_AT in body["fields"]
            assert isinstance(body["fields"][FIELD_CREATED_AT], int)
            assert body["fields"]["来源"] in {"用户提交", "来自发现"}
            assert body["fields"]["办理状态"] == "待服务"
            return _record_response(create_id, body["fields"])
        if request.method == "GET" and "/records/" in request.url.path:
            record_id = request.url.path.rsplit("/", 1)[-1]
            return _record_response(record_id)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    return handler


def test_create_service_case_disabled_does_not_bind_or_call_feishu(client, monkeypatch):
    queued = _capture_background(monkeypatch)
    submission_id = _create_succeeded_submission(client, monkeypatch)
    response = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert response.status_code == 201
    assert response.json()["created"] is True
    assert response.json()["service_case"]["status"] == "open"
    assert _count_bindings() == 0
    assert queued == []


def test_new_case_creates_pending_binding_then_background_sync(client, monkeypatch):
    integration, requests, http_client = _mock_integration(_create_then_search_handler())
    queued = _capture_background(monkeypatch)
    _patch_integration(monkeypatch, integration)
    try:
        submission_id = _create_succeeded_submission(client, monkeypatch)
        response = client.post(
            f"/api/user-submissions/{submission_id}/service-case",
            headers=_header(),
        )
        assert response.status_code == 201
        case_id = UUID(response.json()["service_case"]["id"])
        binding = _get_binding(case_id)
        assert binding is not None
        assert binding.sync_status == FeishuBindingSyncStatus.PENDING.value
        assert binding.record_id is None
        assert queued
        func, args, _kwargs = queued[0]
        assert func is run_service_case_feishu_sync
        func(*args)
        synced = _get_binding(case_id)
        assert synced is not None
        assert synced.sync_status == FeishuBindingSyncStatus.SYNCED.value
        assert synced.record_id == "rec123"
        assert synced.last_synced_at is not None
        assert _get_case(case_id).status == "open"
        assert any(_is_create(item) for item in requests)
    finally:
        http_client.close()


def test_successful_outbound_sync_keeps_service_case_open():
    case_id = _insert_service_case()
    integration, requests, http_client = _mock_integration(_create_then_search_handler())
    db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        binding = ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
        assert binding is not None
        assert binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
        assert binding.record_id == "rec123"
        assert binding.last_synced_at is not None
        assert binding.last_error_code is None
        assert _get_case(case_id).status == "open"
        assert sum(1 for item in requests if _is_create(item)) == 1
    finally:
        db.close()
        http_client.close()


def test_feishu_failure_does_not_rollback_service_case(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return _token_response()
        if _is_search(request):
            return _search_response([])
        if _is_create(request):
            return httpx.Response(500, json={"code": 1, "msg": "internal"})
        raise AssertionError(f"unexpected request {request.url}")

    integration, _requests, http_client = _mock_integration(handler)
    queued = _capture_background(monkeypatch)
    _patch_integration(monkeypatch, integration)
    try:
        submission_id = _create_succeeded_submission(client, monkeypatch)
        response = client.post(
            f"/api/user-submissions/{submission_id}/service-case",
            headers=_header(),
        )
        assert response.status_code == 201
        case_id = UUID(response.json()["service_case"]["id"])
        queued[0][0](*queued[0][1])
        case = _get_case(case_id)
        assert case.status == "open"
        binding = _get_binding(case_id)
        assert binding is not None
        assert binding.sync_status == FeishuBindingSyncStatus.FAILED.value
        assert binding.last_error_code == FeishuErrorCode.REQUEST_FAILED.value
    finally:
        http_client.close()


def test_duplicate_post_does_not_retry_feishu(client, monkeypatch):
    integration, requests, http_client = _mock_integration(_create_then_search_handler())
    queued = _capture_background(monkeypatch)
    _patch_integration(monkeypatch, integration)
    try:
        submission_id = _create_succeeded_submission(client, monkeypatch)
        first = client.post(
            f"/api/user-submissions/{submission_id}/service-case",
            headers=_header(),
        )
        assert first.status_code == 201
        assert first.json()["created"] is True
        queued[0][0](*queued[0][1])
        create_count = sum(1 for item in requests if _is_create(item))
        queued.clear()
        second = client.post(
            f"/api/user-submissions/{submission_id}/service-case",
            headers=_header(),
        )
        assert second.status_code == 200
        assert second.json()["created"] is False
        assert queued == []
        assert sum(1 for item in requests if _is_create(item)) == create_count
    finally:
        http_client.close()


def test_already_synced_is_idempotent():
    case_id = _insert_service_case()
    integration, requests, http_client = _mock_integration(_create_then_search_handler())
    db = SessionLocal()
    try:
        service = ServiceCaseFeishuSyncService(integration=integration)
        binding = FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        FeishuBindingService().mark_synced(db, binding, record_id="rec123")
        before = len(requests)
        again = service.sync_service_case(case_id)
        assert again is not None
        assert again.record_id == "rec123"
        assert again.sync_status == FeishuBindingSyncStatus.SYNCED.value
        assert not any(_is_create(item) for item in requests[before:])
        assert len(requests) == before
    finally:
        db.close()
        http_client.close()


def test_remote_record_already_exists_does_not_create():
    case_id = _insert_service_case()
    integration, requests, http_client = _mock_integration(
        _create_then_search_handler(search_ids=["recEXIST"])
    )
    db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        binding = ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
        assert binding is not None
        assert binding.record_id == "recEXIST"
        assert binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
        assert not any(_is_create(item) for item in requests)
    finally:
        db.close()
        http_client.close()


def test_duplicate_remote_case_ids_fail_without_create():
    case_id = _insert_service_case()
    integration, requests, http_client = _mock_integration(
        _create_then_search_handler(search_ids=["rec1", "rec2"])
    )
    db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        binding = ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
        assert binding is not None
        assert binding.sync_status == FeishuBindingSyncStatus.FAILED.value
        assert binding.last_error_code == FeishuErrorCode.DUPLICATE_CASE_RECORDS.value
        assert not any(_is_create(item) for item in requests)
        assert _get_case(case_id).status == "open"
    finally:
        db.close()
        http_client.close()


def test_timeout_reconciliation_success():
    case_id = _insert_service_case()
    searches = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return _token_response()
        if _is_search(request):
            searches["count"] += 1
            if searches["count"] == 1:
                return _search_response([])
            return _search_response(["rec123"])
        if _is_create(request):
            raise httpx.TimeoutException("timed out")
        raise AssertionError(f"unexpected request {request.url}")

    integration, requests, http_client = _mock_integration(handler)
    db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        binding = ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
        assert binding is not None
        assert binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
        assert binding.record_id == "rec123"
        assert sum(1 for item in requests if _is_create(item)) == 1
    finally:
        db.close()
        http_client.close()


def test_timeout_reconciliation_empty_does_not_create_again():
    case_id = _insert_service_case()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return _token_response()
        if _is_search(request):
            return _search_response([])
        if _is_create(request):
            raise httpx.TimeoutException("timed out")
        raise AssertionError(f"unexpected request {request.url}")

    integration, requests, http_client = _mock_integration(handler)
    db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        binding = ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
        assert binding is not None
        assert binding.sync_status == FeishuBindingSyncStatus.FAILED.value
        assert binding.last_error_code == FeishuErrorCode.TIMEOUT.value
        assert sum(1 for item in requests if _is_create(item)) == 1
    finally:
        db.close()
        http_client.close()


def test_existing_record_id_confirms_without_create():
    case_id = _insert_service_case()
    integration, requests, http_client = _mock_integration(_create_then_search_handler())
    db = SessionLocal()
    try:
        binding = FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        binding.record_id = "rec123"
        save_binding(db, binding)
        result = ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
        assert result is not None
        assert result.sync_status == FeishuBindingSyncStatus.SYNCED.value
        assert result.record_id == "rec123"
        assert not any(_is_create(item) for item in requests)
        assert any(item.method == "GET" for item in requests)
    finally:
        db.close()
        http_client.close()


def test_missing_remote_record_marks_failed_without_create():
    case_id = _insert_service_case()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return _token_response()
        if request.method == "GET":
            return httpx.Response(200, json={"code": 1254043, "msg": "record not found"})
        raise AssertionError("must not create or search when bound record is missing")

    integration, requests, http_client = _mock_integration(handler)
    db = SessionLocal()
    try:
        binding = FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        binding.record_id = "recGONE"
        save_binding(db, binding)
        result = ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
        assert result is not None
        assert result.sync_status == FeishuBindingSyncStatus.FAILED.value
        assert result.last_error_code == FeishuErrorCode.RECORD_NOT_FOUND.value
        assert result.record_id == "recGONE"
        assert not any(_is_create(item) for item in requests)
    finally:
        db.close()
        http_client.close()


def test_background_sync_uses_independent_session():
    case_id = _insert_service_case()
    integration, _requests, http_client = _mock_integration(_create_then_search_handler())
    request_db = SessionLocal()
    try:
        FeishuBindingService().create_pending_binding(
            request_db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
    finally:
        request_db.close()
    try:
        binding = ServiceCaseFeishuSyncService(integration=integration).sync_service_case(case_id)
        assert binding is not None
        assert binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
        assert binding.record_id == "rec123"
    finally:
        http_client.close()


def test_historical_cases_are_not_backfilled(client):
    case_id = _insert_service_case()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert _get_binding(case_id) is None
    assert _count_bindings() == 0


def test_cli_explicit_sync_for_historical_case(monkeypatch, capsys):
    case_id = _insert_service_case()
    integration, requests, http_client = _mock_integration(
        _create_then_search_handler(create_id="recCLI")
    )
    _patch_integration(monkeypatch, integration)
    try:
        assert _get_binding(case_id) is None
        code = sync_cli_main([str(case_id)])
        assert code == 0
        output = capsys.readouterr().out
        assert f"ServiceCase: {case_id}" in output
        assert "Binding: synced" in output
        assert "Record ID: recCLI" in output
        assert APP_SECRET not in output
        assert TENANT_TOKEN not in output
        assert "Authorization" not in output
        binding = _get_binding(case_id)
        assert binding is not None
        assert binding.record_id == "recCLI"
        assert any(_is_create(item) for item in requests)
    finally:
        http_client.close()


def test_cli_prints_sanitized_provider_error(monkeypatch, capsys, caplog):
    case_id = _insert_service_case()
    provider_msg = (
        f"Access denied. One of the following scopes is required: bitable:app "
        f"secret={APP_SECRET} tenant_access_token={TENANT_TOKEN}"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return _token_response()
        if _is_search(request):
            return httpx.Response(200, json={"code": 1254301, "msg": provider_msg})
        raise AssertionError("must not create after provider search error")

    integration, _requests, http_client = _mock_integration(handler)
    _patch_integration(monkeypatch, integration)
    try:
        with caplog.at_level("WARNING"):
            code = sync_cli_main([str(case_id)])
        assert code == 1
        output = capsys.readouterr().out
        assert f"ServiceCase: {case_id}" in output
        assert "Binding: failed" in output
        assert "Error: FEISHU_REQUEST_FAILED" in output
        assert "Provider code: 1254301" in output
        assert "Provider message:" in output
        assert "Access denied" in output
        assert "bitable:app" in output
        assert APP_SECRET not in output
        assert TENANT_TOKEN not in output
        assert "Authorization" not in output
        logs = caplog.text
        assert "provider_code=1254301" in logs
        assert "FEISHU_REQUEST_FAILED" in logs
        assert "Access denied" in logs
        assert APP_SECRET not in logs
        assert TENANT_TOKEN not in logs
    finally:
        http_client.close()


def test_enabled_but_incomplete_config_still_creates_service_case(client, monkeypatch):
    monkeypatch.setattr(settings, "FEISHU_ENABLED", True)
    monkeypatch.setattr(settings, "FEISHU_APP_ID", "")
    monkeypatch.setattr(settings, "FEISHU_APP_SECRET", SecretStr(""))
    monkeypatch.setattr(settings, "FEISHU_BITABLE_APP_TOKEN", "")
    monkeypatch.setattr(settings, "FEISHU_SERVICE_CASE_TABLE_ID", "")
    queued = _capture_background(monkeypatch)
    submission_id = _create_succeeded_submission(client, monkeypatch)
    response = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert response.status_code == 201
    assert response.json()["created"] is True
    assert _count_bindings() == 0
    assert queued == []


def test_no_public_feishu_retry_endpoint(client):
    payload = client.get("/openapi.json").json()
    paths = payload["paths"]
    assert not any("feishu" in path.lower() for path in paths)
    assert "/api/service-cases/{service_case_id}/retry-feishu" not in paths
