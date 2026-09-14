"""Process-local Feishu tenant_access_token cache.

Does not persist tokens. Does not log APP_SECRET or the token value.
"""

from __future__ import annotations

import threading
from datetime import timedelta

from app.core.time import utc_now
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError

TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
TOKEN_EXPIRY_SAFETY_SECONDS = 60


class FeishuTenantTokenProvider:
    def __init__(self, client: object, config: FeishuConfig) -> None:
        self._client = client
        self._config = config
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at = utc_now()

    def get_token(self) -> str:
        with self._lock:
            if self._token and utc_now() < self._expires_at - timedelta(seconds=TOKEN_EXPIRY_SAFETY_SECONDS):
                return self._token
            token, expire_seconds = self._fetch_token()
            self._token = token
            self._expires_at = utc_now() + timedelta(seconds=max(int(expire_seconds), 0))
            return token

    def clear(self) -> None:
        with self._lock:
            self._token = None
            self._expires_at = utc_now()

    def _fetch_token(self) -> tuple[str, int]:
        self._require_auth_config()
        payload = self._client.request_json(
            "POST",
            TOKEN_PATH,
            json={"app_id": self._config.app_id, "app_secret": self._config.app_secret},
            authenticate=False,
        )
        token = str(payload.get("tenant_access_token") or "").strip()
        expire = payload.get("expire")
        if not token:
            raise FeishuIntegrationError(
                FeishuErrorCode.AUTH_FAILED,
                "Feishu token response did not include a tenant access token",
                retryable=False,
                secrets=self._secrets(),
            )
        try:
            expire_seconds = int(expire)
        except (TypeError, ValueError):
            expire_seconds = 0
        return token, expire_seconds

    def _require_auth_config(self) -> None:
        if not self._config.is_auth_configured():
            raise FeishuIntegrationError(
                FeishuErrorCode.NOT_CONFIGURED,
                "Feishu is disabled or missing app credentials",
                retryable=False,
            )

    def _secrets(self) -> tuple[str, ...]:
        return tuple(item for item in (self._config.app_secret, self._token) if item)
