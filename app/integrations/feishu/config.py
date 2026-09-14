"""Feishu integration settings loaded from the unified application Settings."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import SecretStr

from app.core.config import Settings, settings


@dataclass
class FeishuConfig:
    enabled: bool
    app_id: str
    app_secret: str = field(repr=False)
    base_url: str
    bitable_app_token: str
    service_case_table_id: str
    timeout_seconds: float

    @classmethod
    def from_settings(cls, values: Settings | None = None) -> FeishuConfig:
        current = values or settings
        secret = current.FEISHU_APP_SECRET
        if isinstance(secret, SecretStr):
            secret_value = secret.get_secret_value()
        else:
            secret_value = str(secret or "")
        return cls(
            enabled=bool(current.FEISHU_ENABLED),
            app_id=(current.FEISHU_APP_ID or "").strip(),
            app_secret=(secret_value or "").strip(),
            base_url=(current.FEISHU_BASE_URL or "https://open.feishu.cn").rstrip("/"),
            bitable_app_token=(current.FEISHU_BITABLE_APP_TOKEN or "").strip(),
            service_case_table_id=(current.FEISHU_SERVICE_CASE_TABLE_ID or "").strip(),
            timeout_seconds=float(current.FEISHU_REQUEST_TIMEOUT_SECONDS),
        )

    def is_auth_configured(self) -> bool:
        return bool(self.enabled and self.app_id and self.app_secret)

    def is_bitable_configured(self) -> bool:
        return bool(
            self.is_auth_configured()
            and self.bitable_app_token
            and self.service_case_table_id
        )
