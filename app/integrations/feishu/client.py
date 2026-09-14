"""Generic Feishu Open API HTTP client.

Callers must not set Authorization. Business code != 0 is treated as an error
even when HTTP status is 200. No implicit retries.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError, sanitize_feishu_text

logger = get_logger(__name__)

AUTH_PROVIDER_CODES = {10003, 10010, 10012, 10013, 10014, 99991661, 99991663, 99991664}
RATE_LIMIT_PROVIDER_CODES = {99991400, 99991401, 99991402}


class FeishuClient:
    def __init__(self, http_client: httpx.Client, config: FeishuConfig) -> None:
        self._http = http_client
        self._config = config
        self._token_provider = None

    def set_token_provider(self, token_provider: object) -> None:
        self._token_provider = token_provider

    def request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        authenticate: bool = True,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if authenticate:
            if self._token_provider is None:
                raise FeishuIntegrationError(
                    FeishuErrorCode.NOT_CONFIGURED,
                    "Feishu token provider is not bound",
                    retryable=False,
                )
            token = self._token_provider.get_token()
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = self._http.request(method, path, json=json, headers=headers or None)
        except httpx.TimeoutException as exc:
            raise FeishuIntegrationError(
                FeishuErrorCode.TIMEOUT,
                "Feishu request timed out",
                retryable=True,
                secrets=self._secrets(),
            ) from exc
        except httpx.RequestError as exc:
            raise FeishuIntegrationError(
                FeishuErrorCode.NETWORK_ERROR,
                "Feishu network error",
                retryable=True,
                secrets=self._secrets(),
            ) from exc

        payload = self._parse_json(response)
        self._raise_for_feishu_payload(response, payload, authenticate=authenticate)
        return payload

    def _parse_json(self, response: httpx.Response) -> dict[str, Any] | None:
        if not response.content:
            return None
        try:
            payload = response.json()
        except ValueError as exc:
            if response.status_code == 429:
                raise FeishuIntegrationError(
                    FeishuErrorCode.RATE_LIMITED,
                    "Feishu rate limited",
                    retryable=True,
                    secrets=self._secrets(),
                ) from exc
            if response.status_code >= 400:
                raise self._http_status_error(response.status_code) from exc
            raise FeishuIntegrationError(
                FeishuErrorCode.INVALID_RESPONSE,
                "Feishu returned a non-JSON response",
                retryable=False,
                secrets=self._secrets(),
            ) from exc
        if payload is not None and not isinstance(payload, dict):
            raise FeishuIntegrationError(
                FeishuErrorCode.INVALID_RESPONSE,
                "Feishu returned an unexpected JSON shape",
                retryable=False,
                secrets=self._secrets(),
            )
        return payload

    def _raise_for_feishu_payload(
        self,
        response: httpx.Response,
        payload: dict[str, Any] | None,
        *,
        authenticate: bool,
    ) -> None:
        if response.status_code == 429:
            raise FeishuIntegrationError(
                FeishuErrorCode.RATE_LIMITED,
                self._provider_message(payload) or "Feishu rate limited",
                retryable=True,
                provider_code=self._provider_code(payload),
                secrets=self._secrets(),
            )
        provider_code = self._provider_code(payload)
        if provider_code not in (None, 0):
            if not authenticate:
                raise FeishuIntegrationError(
                    FeishuErrorCode.AUTH_FAILED,
                    self._provider_message(payload) or "Feishu token request failed",
                    retryable=False,
                    provider_code=provider_code,
                    secrets=self._secrets(),
                )
            raise self._business_error(provider_code, payload)
        if response.status_code >= 400:
            if not authenticate:
                raise FeishuIntegrationError(
                    FeishuErrorCode.AUTH_FAILED,
                    self._provider_message(payload) or f"Feishu HTTP {response.status_code}",
                    retryable=False,
                    provider_code=response.status_code,
                    secrets=self._secrets(),
                )
            raise self._http_status_error(response.status_code, payload)

    def _business_error(self, provider_code: object, payload: dict[str, Any] | None) -> FeishuIntegrationError:
        message = self._provider_message(payload) or "Feishu business error"
        if provider_code in RATE_LIMIT_PROVIDER_CODES:
            code = FeishuErrorCode.RATE_LIMITED
        elif provider_code in AUTH_PROVIDER_CODES:
            code = FeishuErrorCode.AUTH_FAILED
        else:
            code = FeishuErrorCode.REQUEST_FAILED
        return FeishuIntegrationError(
            code,
            message,
            provider_code=provider_code,
            secrets=self._secrets(),
        )

    def _http_status_error(
        self,
        status_code: int,
        payload: dict[str, Any] | None = None,
    ) -> FeishuIntegrationError:
        if status_code in {401, 403}:
            code = FeishuErrorCode.AUTH_FAILED
        else:
            code = FeishuErrorCode.REQUEST_FAILED
        message = self._provider_message(payload) or f"Feishu HTTP {status_code}"
        return FeishuIntegrationError(
            code,
            message,
            provider_code=status_code,
            secrets=self._secrets(),
        )

    def _provider_code(self, payload: dict[str, Any] | None) -> object | None:
        if not payload:
            return None
        return payload.get("code")

    def _provider_message(self, payload: dict[str, Any] | None) -> str:
        if not payload:
            return ""
        return sanitize_feishu_text(str(payload.get("msg") or payload.get("message") or ""), self._secrets())

    def _secrets(self) -> tuple[str, ...]:
        token = None
        if self._token_provider is not None:
            token = getattr(self._token_provider, "_token", None)
        return tuple(item for item in (self._config.app_secret, token) if item)
