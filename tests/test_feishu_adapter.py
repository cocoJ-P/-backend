"""Feishu official SDK adapter tests. SDK Client is faked; no internet."""

from __future__ import annotations

import lark_oapi as lark
import pytest
import requests
from lark_oapi.core.exception import ObtainAccessTokenException, UnmarshalException

from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError, format_safe_feishu_error
from app.integrations.feishu.schemas import FeishuBitableRecord
from app.integrations.feishu.sdk import create_feishu_sdk_client, get_shared_sdk_client, reset_shared_sdk_client
from app.integrations.feishu.service import create_feishu_integration
from tests.feishu_sdk_fakes import FakeSdkRecord, FakeSdkResponse, make_fake_sdk

APP_SECRET = "super-secret-app-secret"
TENANT_TOKEN = "t-test-tenant-access-token"
APP_TOKEN = "bascn_test_app"
TABLE_ID = "tbl_test_service_case"


def _enabled_config(**overrides) -> FeishuConfig:
    values = {
        "enabled": True,
        "app_id": "cli_test_app",
        "app_secret": APP_SECRET,
        "base_url": "https://open.feishu.cn",
        "bitable_app_token": APP_TOKEN,
        "service_case_table_id": TABLE_ID,
        "timeout_seconds": 10,
    }
    values.update(overrides)
    return FeishuConfig(**values)


def _disabled_config() -> FeishuConfig:
    return _enabled_config(
        enabled=False,
        app_id="",
        app_secret="",
        bitable_app_token="",
        service_case_table_id="",
    )


def _integration(handler):
    sdk, calls = make_fake_sdk(handler)
    integration = create_feishu_integration(config=_enabled_config(), sdk_client=sdk)
    return integration, calls


@pytest.fixture(autouse=True)
def _reset_sdk_client():
    reset_shared_sdk_client()
    yield
    reset_shared_sdk_client()


def test_sdk_client_builder_receives_credentials_without_network(monkeypatch):
    captured: dict = {}

    class FakeBuilder:
        def app_id(self, value):
            captured["app_id"] = value
            return self

        def app_secret(self, value):
            captured["app_secret"] = value
            return self

        def log_level(self, value):
            captured["log_level"] = value
            return self

        def timeout(self, value):
            captured["timeout"] = value
            return self

        def domain(self, value):
            captured["domain"] = value
            return self

        def build(self):
            captured["built"] = True
            return object()

    monkeypatch.setattr("app.integrations.feishu.sdk.lark.Client.builder", lambda: FakeBuilder())
    client = create_feishu_sdk_client(_enabled_config())
    assert client is not None
    assert captured["app_id"] == "cli_test_app"
    assert captured["app_secret"] == APP_SECRET
    assert captured["timeout"] == 10
    assert captured["log_level"] == lark.LogLevel.WARNING
    assert captured["domain"] == "https://open.feishu.cn"
    assert captured["built"] is True
    assert captured["log_level"] != lark.LogLevel.DEBUG


def test_shared_sdk_client_is_reused(monkeypatch):
    builds = {"count": 0}

    class FakeBuilder:
        def app_id(self, value):
            return self

        def app_secret(self, value):
            return self

        def log_level(self, value):
            return self

        def timeout(self, value):
            return self

        def domain(self, value):
            return self

        def build(self):
            builds["count"] += 1
            return object()

    monkeypatch.setattr("app.integrations.feishu.sdk.lark.Client.builder", lambda: FakeBuilder())
    first = get_shared_sdk_client(_enabled_config())
    second = get_shared_sdk_client(_enabled_config())
    assert first is second
    assert builds["count"] == 1


def test_disabled_adapter_does_not_construct_sdk(monkeypatch):
    def boom():
        raise AssertionError("disabled adapter must not construct SDK")

    monkeypatch.setattr("app.integrations.feishu.sdk.lark.Client.builder", boom)
    integration = create_feishu_integration(config=_disabled_config())
    assert integration.sdk_client is None
    assert not hasattr(integration, "token_provider")
    with pytest.raises(FeishuIntegrationError) as exc:
        integration.bitable.create_record({"任意字段": "value"})
    assert exc.value.code == FeishuErrorCode.NOT_CONFIGURED
    assert exc.value.retryable is False


def test_enabled_but_missing_credentials_is_not_configured(monkeypatch):
    def boom():
        raise AssertionError("misconfigured adapter must not construct SDK")

    monkeypatch.setattr("app.integrations.feishu.sdk.lark.Client.builder", boom)
    config = _enabled_config(
        app_id="",
        app_secret="",
        bitable_app_token="",
        service_case_table_id="",
    )
    integration = create_feishu_integration(config=config)
    with pytest.raises(FeishuIntegrationError) as exc:
        integration.bitable.create_record({"任意字段": "value"})
    assert exc.value.code == FeishuErrorCode.NOT_CONFIGURED
    assert APP_SECRET not in str(exc.value)


def test_bitable_create_record_converts_sdk_model_to_dto():
    def handler(operation, request):
        assert operation == "create"
        assert request.app_token == APP_TOKEN
        assert request.table_id == TABLE_ID
        assert request.request_body.fields == {"任意字段": "value"}
        return FakeSdkResponse(record=FakeSdkRecord("recCREATE", {"任意字段": "value"}))

    integration, calls = _integration(handler)
    record = integration.bitable.create_record({"任意字段": "value"})
    assert isinstance(record, FeishuBitableRecord)
    assert record.record_id == "recCREATE"
    assert record.fields == {"任意字段": "value"}
    assert len(calls) == 1


def test_bitable_get_record_parses_typed_result():
    def handler(operation, request):
        assert operation == "get"
        assert request.record_id == "recGET"
        return FakeSdkResponse(record=FakeSdkRecord("recGET", {"状态": "open"}))

    integration, _calls = _integration(handler)
    record = integration.bitable.get_record("recGET")
    assert record.record_id == "recGET"
    assert record.fields == {"状态": "open"}
    assert not isinstance(record, FakeSdkRecord)


def test_bitable_update_record_sends_fields_payload():
    def handler(operation, request):
        assert operation == "update"
        assert request.record_id == "recUPD"
        assert request.request_body.fields == {"进度": "处理中"}
        return FakeSdkResponse(record=FakeSdkRecord("recUPD", {"进度": "处理中"}))

    integration, _calls = _integration(handler)
    record = integration.bitable.update_record("recUPD", {"进度": "处理中"})
    assert record.record_id == "recUPD"
    assert record.fields == {"进度": "处理中"}


def test_bitable_search_records_puts_filter_in_request_body():
    case_id = "e29d472b-8a72-45a6-bc10-14364e7fa66e"

    def handler(operation, request):
        assert operation == "search"
        assert request.page_size == 20
        assert ("page_size", "20") in request.queries
        body = request.request_body
        assert body.filter is not None
        condition = body.filter.conditions[0]
        assert condition.field_name == "Case ID"
        assert condition.operator == "is"
        assert condition.value == [case_id]
        assert "filter" not in dict(request.queries)
        return FakeSdkResponse(items=[FakeSdkRecord("recSEARCH", {"Case ID": case_id})])

    integration, _calls = _integration(handler)
    records = integration.bitable.search_records(
        filter={
            "conjunction": "and",
            "conditions": [{"field_name": "Case ID", "operator": "is", "value": [case_id]}],
        }
    )
    assert [item.record_id for item in records] == ["recSEARCH"]
    assert records[0].fields["Case ID"] == case_id


def test_sdk_business_error_field_name_not_found():
    def handler(operation, request):
        return FakeSdkResponse(code=1254045, msg="FieldNameNotFound", log_id="log-abc")

    integration, calls = _integration(handler)
    with pytest.raises(FeishuIntegrationError) as exc:
        integration.bitable.create_record({"创建时间": "bad"})
    error = exc.value
    assert error.code == FeishuErrorCode.REQUEST_FAILED
    assert error.provider_code == 1254045
    assert error.message == "FieldNameNotFound"
    assert error.log_id == "log-abc"
    assert error.retryable is False
    assert len(calls) == 1
    report = format_safe_feishu_error(error)
    assert "Provider code: 1254045" in report
    assert "Log id: log-abc" in report
    assert "FieldNameNotFound" in report


def test_sdk_auth_exception_does_not_expose_secret():
    def handler(operation, request):
        raise ObtainAccessTokenException(
            "failed",
            10014,
            f"app secret invalid {APP_SECRET} tenant_access_token={TENANT_TOKEN}",
        )

    integration, _calls = _integration(handler)
    with pytest.raises(FeishuIntegrationError) as exc:
        integration.bitable.get_record("rec1")
    error = exc.value
    assert error.code == FeishuErrorCode.AUTH_FAILED
    assert error.retryable is False
    assert error.provider_code == 10014
    assert APP_SECRET not in str(error)
    assert APP_SECRET not in repr(error)
    assert TENANT_TOKEN not in str(error)
    assert TENANT_TOKEN not in repr(error)
    assert APP_SECRET not in format_safe_feishu_error(error)


def test_client_timeout_is_retryable():
    def handler(operation, request):
        raise requests.Timeout("timed out")

    integration, calls = _integration(handler)
    with pytest.raises(FeishuIntegrationError) as exc:
        integration.bitable.get_record("rec1")
    assert exc.value.code == FeishuErrorCode.TIMEOUT
    assert exc.value.retryable is True
    assert len(calls) == 1


def test_client_network_error_is_retryable():
    def handler(operation, request):
        raise requests.ConnectionError("connection refused")

    integration, _calls = _integration(handler)
    with pytest.raises(FeishuIntegrationError) as exc:
        integration.bitable.get_record("rec1")
    assert exc.value.code == FeishuErrorCode.NETWORK_ERROR
    assert exc.value.retryable is True


def test_client_rate_limit_is_retryable_without_retry():
    def handler(operation, request):
        return FakeSdkResponse(code=99991400, msg="rate limited")

    integration, calls = _integration(handler)
    with pytest.raises(FeishuIntegrationError) as exc:
        integration.bitable.get_record("rec1")
    assert exc.value.code == FeishuErrorCode.RATE_LIMITED
    assert exc.value.retryable is True
    assert len(calls) == 1


def test_client_invalid_response_maps_to_invalid_response():
    def handler(operation, request):
        raise UnmarshalException(dict, str, "data")

    integration, _calls = _integration(handler)
    with pytest.raises(FeishuIntegrationError) as exc:
        integration.bitable.get_record("rec1")
    assert exc.value.code == FeishuErrorCode.INVALID_RESPONSE
    assert exc.value.retryable is False


def test_create_record_does_not_auto_retry_on_failure():
    def handler(operation, request):
        return FakeSdkResponse(code=1, msg="internal")

    integration, calls = _integration(handler)
    with pytest.raises(FeishuIntegrationError) as exc:
        integration.bitable.create_record({"任意字段": "value"})
    assert exc.value.code == FeishuErrorCode.REQUEST_FAILED
    assert [item[0] for item in calls] == ["create"]


def test_error_str_repr_do_not_leak_secrets():
    error = FeishuIntegrationError(
        FeishuErrorCode.AUTH_FAILED,
        f"failed with {APP_SECRET} and {TENANT_TOKEN}",
        secrets=(APP_SECRET, TENANT_TOKEN),
    )
    assert APP_SECRET not in str(error)
    assert APP_SECRET not in repr(error)
    assert TENANT_TOKEN not in str(error)
    assert TENANT_TOKEN not in repr(error)
    assert error.retryable is False


def test_format_safe_feishu_error_includes_provider_fields_without_secrets():
    error = FeishuIntegrationError(
        FeishuErrorCode.REQUEST_FAILED,
        f"Access denied {APP_SECRET} Authorization: Bearer {TENANT_TOKEN}",
        provider_code=1254301,
        secrets=(APP_SECRET, TENANT_TOKEN),
    )
    report = format_safe_feishu_error(error)
    assert "Error: FEISHU_REQUEST_FAILED" in report
    assert "Provider code: 1254301" in report
    assert "Provider message:" in report
    assert "Access denied" in report
    assert APP_SECRET not in report
    assert TENANT_TOKEN not in report
    assert "Authorization" not in report


def test_app_starts_with_feishu_disabled(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    payload = client.get("/openapi.json").json()
    assert not any("feishu" in path.lower() for path in payload["paths"])
    assert "/api/service-cases" in payload["paths"]
    assert "/api/service-cases/{service_case_id}/feishu" not in payload["paths"]
    assert "/api/service-cases/{service_case_id}/feishu-binding" not in payload["paths"]


def test_feishu_config_repr_hides_app_secret():
    config = _enabled_config()
    assert APP_SECRET not in repr(config)
    assert "app_secret" not in repr(config)


def test_ws_client_factory_passes_credentials_without_connecting(monkeypatch):
    captured: dict = {}

    class FakeWsClient:
        def __init__(self, app_id, app_secret, **kwargs):
            captured["app_id"] = app_id
            captured["app_secret"] = app_secret
            captured.update(kwargs)

        def start(self):
            raise AssertionError("D6.5.1 must not start WebSocket from factory")

    monkeypatch.setattr("app.integrations.feishu.events.ws.lark.ws.Client", FakeWsClient)
    from app.integrations.feishu.events.ws import create_feishu_ws_client

    client = create_feishu_ws_client(config=_enabled_config())
    assert client is not None
    assert captured["app_id"] == "cli_test_app"
    assert captured["app_secret"] == APP_SECRET
    assert captured["log_level"] == lark.LogLevel.WARNING
    assert captured["auto_reconnect"] is True
    assert captured["domain"] == "https://open.feishu.cn"
    assert captured["event_handler"] is not None
    assert APP_SECRET not in repr(captured["event_handler"])


def test_ws_client_factory_disabled_does_not_connect(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("disabled WS factory must not construct client")

    monkeypatch.setattr("app.integrations.feishu.events.ws.lark.ws.Client", boom)
    from app.integrations.feishu.events.ws import create_feishu_ws_client

    with pytest.raises(FeishuIntegrationError) as exc:
        create_feishu_ws_client(config=_disabled_config())
    assert exc.value.code == FeishuErrorCode.NOT_CONFIGURED
