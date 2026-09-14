"""Feishu adapter foundation tests. All HTTP is mocked; no internet."""

from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest

from app.core.time import utc_now
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError, format_safe_feishu_error
from app.integrations.feishu.service import create_feishu_integration
from app.integrations.feishu.token_provider import TOKEN_PATH, TOKEN_EXPIRY_SAFETY_SECONDS

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


def _token_payload(token: str = TENANT_TOKEN, expire: int = 7200) -> dict:
    return {
        "code": 0,
        "msg": "ok",
        "tenant_access_token": token,
        "expire": expire,
    }


def _record_payload(record_id: str = "recABC", fields: dict | None = None) -> dict:
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "record": {
                "record_id": record_id,
                "fields": fields or {},
            }
        },
    }


def _integration(handler):
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


def test_token_fetched_once_on_first_call():
    token_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            token_calls["count"] += 1
            body = json.loads(request.content)
            assert body["app_id"] == "cli_test_app"
            assert request.headers.get("Authorization") is None
            return httpx.Response(200, json=_token_payload())
        raise AssertionError(f"unexpected request: {request.url}")

    integration, requests, http_client = _integration(handler)
    try:
        token = integration.token_provider.get_token()
        assert token == TENANT_TOKEN
        assert token_calls["count"] == 1
        assert len(requests) == 1
    finally:
        http_client.close()


def test_token_is_cached_on_second_call():
    token_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            token_calls["count"] += 1
            return httpx.Response(200, json=_token_payload())
        raise AssertionError(f"unexpected request: {request.url}")

    integration, _requests, http_client = _integration(handler)
    try:
        assert integration.token_provider.get_token() == TENANT_TOKEN
        assert integration.token_provider.get_token() == TENANT_TOKEN
        assert token_calls["count"] == 1
    finally:
        http_client.close()


def test_token_refreshed_inside_expiry_safety_window():
    token_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            token_calls["count"] += 1
            token = TENANT_TOKEN if token_calls["count"] == 1 else "t-refreshed-token"
            return httpx.Response(200, json=_token_payload(token=token))
        raise AssertionError(f"unexpected request: {request.url}")

    integration, _requests, http_client = _integration(handler)
    try:
        assert integration.token_provider.get_token() == TENANT_TOKEN
        integration.token_provider._expires_at = utc_now() + timedelta(
            seconds=TOKEN_EXPIRY_SAFETY_SECONDS - 10
        )
        assert integration.token_provider.get_token() == "t-refreshed-token"
        assert token_calls["count"] == 2
    finally:
        http_client.close()


def test_token_auth_failure_does_not_expose_secret():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(
                200,
                json={
                    "code": 10014,
                    "msg": f"app secret invalid {APP_SECRET}",
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    integration, _requests, http_client = _integration(handler)
    try:
        with pytest.raises(FeishuIntegrationError) as exc:
            integration.token_provider.get_token()
        error = exc.value
        assert error.code == FeishuErrorCode.AUTH_FAILED
        assert error.retryable is False
        assert APP_SECRET not in str(error)
        assert APP_SECRET not in repr(error)
        assert TENANT_TOKEN not in str(error)
        assert TENANT_TOKEN not in repr(error)
    finally:
        http_client.close()


def test_bitable_request_sets_authorization_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json=_token_payload())
        seen["authorization"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_record_payload("recCREATE", {"任意字段": "value"}))

    integration, _requests, http_client = _integration(handler)
    try:
        record = integration.bitable.create_record({"任意字段": "value"})
        assert record.record_id == "recCREATE"
        assert record.fields == {"任意字段": "value"}
        assert seen["authorization"] == f"Bearer {TENANT_TOKEN}"
        assert seen["method"] == "POST"
        assert f"/apps/{APP_TOKEN}/tables/{TABLE_ID}/records" in seen["url"]
        assert seen["body"] == {"fields": {"任意字段": "value"}}
    finally:
        http_client.close()


def test_client_http_500_maps_to_request_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json=_token_payload())
        return httpx.Response(500, json={"code": 0, "msg": "internal"})

    integration, _requests, http_client = _integration(handler)
    try:
        with pytest.raises(FeishuIntegrationError) as exc:
            integration.bitable.get_record("rec1")
        assert exc.value.code == FeishuErrorCode.REQUEST_FAILED
        assert exc.value.retryable is False
    finally:
        http_client.close()


def test_client_timeout_is_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json=_token_payload())
        raise httpx.TimeoutException("timed out")

    integration, requests, http_client = _integration(handler)
    try:
        with pytest.raises(FeishuIntegrationError) as exc:
            integration.bitable.get_record("rec1")
        assert exc.value.code == FeishuErrorCode.TIMEOUT
        assert exc.value.retryable is True
        assert len([item for item in requests if item.url.path != TOKEN_PATH]) == 1
    finally:
        http_client.close()


def test_client_network_error_is_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json=_token_payload())
        raise httpx.ConnectError("connection refused")

    integration, _requests, http_client = _integration(handler)
    try:
        with pytest.raises(FeishuIntegrationError) as exc:
            integration.bitable.get_record("rec1")
        assert exc.value.code == FeishuErrorCode.NETWORK_ERROR
        assert exc.value.retryable is True
    finally:
        http_client.close()


def test_client_rate_limit_is_retryable_without_retry():
    calls = {"bitable": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json=_token_payload())
        calls["bitable"] += 1
        return httpx.Response(429, json={"code": 99991400, "msg": "rate limited"})

    integration, _requests, http_client = _integration(handler)
    try:
        with pytest.raises(FeishuIntegrationError) as exc:
            integration.bitable.get_record("rec1")
        assert exc.value.code == FeishuErrorCode.RATE_LIMITED
        assert exc.value.retryable is True
        assert calls["bitable"] == 1
    finally:
        http_client.close()


def test_client_invalid_json_maps_to_invalid_response():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json=_token_payload())
        return httpx.Response(200, text="<html>not json</html>")

    integration, _requests, http_client = _integration(handler)
    try:
        with pytest.raises(FeishuIntegrationError) as exc:
            integration.bitable.get_record("rec1")
        assert exc.value.code == FeishuErrorCode.INVALID_RESPONSE
        assert exc.value.retryable is False
    finally:
        http_client.close()


def test_bitable_get_record_parses_typed_result():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json=_token_payload())
        assert request.method == "GET"
        assert request.url.path.endswith("/records/recGET")
        return httpx.Response(200, json=_record_payload("recGET", {"状态": "open"}))

    integration, _requests, http_client = _integration(handler)
    try:
        record = integration.bitable.get_record("recGET")
        assert record.record_id == "recGET"
        assert record.fields == {"状态": "open"}
    finally:
        http_client.close()


def test_bitable_update_record_sends_fields_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json=_token_payload())
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_record_payload("recUPD", {"进度": "处理中"}))

    integration, _requests, http_client = _integration(handler)
    try:
        record = integration.bitable.update_record("recUPD", {"进度": "处理中"})
        assert record.record_id == "recUPD"
        assert seen["method"] == "PUT"
        assert seen["path"].endswith("/records/recUPD")
        assert seen["body"] == {"fields": {"进度": "处理中"}}
        assert seen["authorization"] == f"Bearer {TENANT_TOKEN}"
    finally:
        http_client.close()


def test_bitable_search_records_posts_generic_filter():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == TOKEN_PATH:
            return httpx.Response(200, json=_token_payload())
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": {
                    "items": [
                        {"record_id": "recSEARCH", "fields": {"任意字段": "value"}},
                    ]
                },
            },
        )

    integration, _requests, http_client = _integration(handler)
    try:
        records = integration.bitable.search_records(
            filter={
                "conjunction": "and",
                "conditions": [{"field_name": "任意字段", "operator": "is", "value": ["value"]}],
            }
        )
        assert [item.record_id for item in records] == ["recSEARCH"]
        assert seen["method"] == "POST"
        assert seen["path"].endswith("/records/search")
        assert "Case ID" not in json.dumps(seen["body"], ensure_ascii=False)
        assert seen["body"]["filter"]["conditions"][0]["field_name"] == "任意字段"
    finally:
        http_client.close()


def test_disabled_adapter_makes_no_external_requests():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("disabled adapter must not call Feishu")

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
        timeout=10,
    )
    integration = create_feishu_integration(config=_disabled_config(), http_client=http_client)
    try:
        with pytest.raises(FeishuIntegrationError) as exc:
            integration.bitable.create_record({"任意字段": "value"})
        assert exc.value.code == FeishuErrorCode.NOT_CONFIGURED
        assert exc.value.retryable is False
        with pytest.raises(FeishuIntegrationError) as token_exc:
            integration.token_provider.get_token()
        assert token_exc.value.code == FeishuErrorCode.NOT_CONFIGURED
    finally:
        http_client.close()


def test_enabled_but_missing_credentials_is_not_configured():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("misconfigured adapter must not call Feishu")

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://open.feishu.cn",
        timeout=10,
    )
    config = _enabled_config(
        app_id="",
        app_secret="",
        bitable_app_token="",
        service_case_table_id="",
    )
    integration = create_feishu_integration(config=config, http_client=http_client)
    try:
        with pytest.raises(FeishuIntegrationError) as exc:
            integration.bitable.create_record({"任意字段": "value"})
        assert exc.value.code == FeishuErrorCode.NOT_CONFIGURED
        assert APP_SECRET not in str(exc.value)
    finally:
        http_client.close()


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
