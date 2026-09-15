"""Official lark-oapi Client factory. Token lifecycle belongs to the SDK."""

from __future__ import annotations

from typing import Any

import lark_oapi as lark
import requests
from lark_oapi.core.exception import (
    AccessDeniedException,
    AccessTokenException,
    NoAuthorizationException,
    ObtainAccessTokenException,
    UnmarshalException,
)

from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import (
    AUTH_PROVIDER_CODES,
    RATE_LIMIT_PROVIDER_CODES,
    FeishuIntegrationError,
    sanitize_feishu_text,
)

_shared_sdk_client: lark.Client | None = None
_shared_sdk_key: tuple[str, str, float] | None = None


def create_feishu_sdk_client(config: FeishuConfig) -> lark.Client:
    if not config.is_auth_configured():
        raise FeishuIntegrationError(
            FeishuErrorCode.NOT_CONFIGURED,
            "Feishu is disabled or missing app credentials",
            retryable=False,
        )
    builder = (
        lark.Client.builder()
        .app_id(config.app_id)
        .app_secret(config.app_secret)
        .log_level(lark.LogLevel.WARNING)
        .timeout(config.timeout_seconds)
    )
    if config.base_url:
        builder = builder.domain(config.base_url)
    return builder.build()


def get_shared_sdk_client(config: FeishuConfig) -> lark.Client:
    global _shared_sdk_client, _shared_sdk_key
    key = (config.app_id, config.base_url, config.timeout_seconds)
    if _shared_sdk_client is None or _shared_sdk_key != key:
        _shared_sdk_client = create_feishu_sdk_client(config)
        _shared_sdk_key = key
    return _shared_sdk_client


def reset_shared_sdk_client() -> None:
    global _shared_sdk_client, _shared_sdk_key
    _shared_sdk_client = None
    _shared_sdk_key = None


def sdk_log_id(response: object) -> str | None:
    getter = getattr(response, "get_log_id", None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    return str(value) if value else None


def raise_for_sdk_response(response: object, *, secrets: tuple[str, ...] = ()) -> None:
    success = getattr(response, "success", None)
    if callable(success) and success():
        return
    provider_code = getattr(response, "code", None)
    message = sanitize_feishu_text(str(getattr(response, "msg", "") or ""), secrets)
    raise FeishuIntegrationError(
        _code_from_provider(provider_code, message),
        message or "Feishu business error",
        provider_code=provider_code,
        log_id=sdk_log_id(response),
        secrets=secrets,
    )


def map_sdk_exception(exc: BaseException, *, secrets: tuple[str, ...] = ()) -> FeishuIntegrationError:
    if isinstance(exc, FeishuIntegrationError):
        return exc
    if isinstance(exc, (TimeoutError, requests.Timeout)):
        return FeishuIntegrationError(
            FeishuErrorCode.TIMEOUT,
            "Feishu request timed out",
            retryable=True,
            secrets=secrets,
        )
    if isinstance(exc, requests.ConnectionError):
        return FeishuIntegrationError(
            FeishuErrorCode.NETWORK_ERROR,
            "Feishu network error",
            retryable=True,
            secrets=secrets,
        )
    if isinstance(
        exc,
        (
            AccessTokenException,
            ObtainAccessTokenException,
            NoAuthorizationException,
            AccessDeniedException,
        ),
    ):
        provider_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        message = str(getattr(exc, "msg", None) or getattr(exc, "error_description", None) or exc)
        return FeishuIntegrationError(
            FeishuErrorCode.AUTH_FAILED,
            message or "Feishu authentication failed",
            retryable=False,
            provider_code=provider_code,
            secrets=secrets,
        )
    if isinstance(exc, UnmarshalException):
        return FeishuIntegrationError(
            FeishuErrorCode.INVALID_RESPONSE,
            "Feishu returned an unexpected response shape",
            retryable=False,
            secrets=secrets,
        )
    return FeishuIntegrationError(
        FeishuErrorCode.REQUEST_FAILED,
        str(exc) or "Feishu request failed",
        retryable=False,
        secrets=secrets,
    )


def invoke_sdk(operation: Any, *, secrets: tuple[str, ...] = ()) -> Any:
    try:
        response = operation()
    except FeishuIntegrationError:
        raise
    except Exception as exc:
        raise map_sdk_exception(exc, secrets=secrets) from exc
    raise_for_sdk_response(response, secrets=secrets)
    return response


def _code_from_provider(provider_code: object, message: str) -> FeishuErrorCode:
    if provider_code in RATE_LIMIT_PROVIDER_CODES or provider_code == 429:
        return FeishuErrorCode.RATE_LIMITED
    if provider_code in AUTH_PROVIDER_CODES or provider_code in {401, 403}:
        return FeishuErrorCode.AUTH_FAILED
    if provider_code == 99991400 or "rate limit" in (message or "").lower():
        return FeishuErrorCode.RATE_LIMITED
    return FeishuErrorCode.REQUEST_FAILED
