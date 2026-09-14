"""Generic Feishu Bitable operations. No ServiceCase field mapping."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.integrations.feishu.client import FeishuClient
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError
from app.integrations.feishu.schemas import FeishuBitableRecord


class FeishuBitableAdapter:
    def __init__(self, client: FeishuClient, config: FeishuConfig) -> None:
        self._client = client
        self._config = config

    def create_record(
        self,
        fields: Mapping[str, Any],
        *,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> FeishuBitableRecord:
        app_token, table_id = self._resolve_table(app_token, table_id)
        payload = self._client.request_json(
            "POST",
            self._records_path(app_token, table_id),
            json={"fields": dict(fields)},
        )
        return self._parse_record(payload)

    def get_record(
        self,
        record_id: str,
        *,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> FeishuBitableRecord:
        app_token, table_id = self._resolve_table(app_token, table_id)
        payload = self._client.request_json(
            "GET",
            self._record_path(app_token, table_id, record_id),
        )
        return self._parse_record(payload)

    def update_record(
        self,
        record_id: str,
        fields: Mapping[str, Any],
        *,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> FeishuBitableRecord:
        app_token, table_id = self._resolve_table(app_token, table_id)
        payload = self._client.request_json(
            "PUT",
            self._record_path(app_token, table_id, record_id),
            json={"fields": dict(fields)},
        )
        return self._parse_record(payload)

    def _resolve_table(self, app_token: str | None, table_id: str | None) -> tuple[str, str]:
        if not self._config.is_bitable_configured() and not (app_token and table_id and self._config.is_auth_configured()):
            raise FeishuIntegrationError(
                FeishuErrorCode.NOT_CONFIGURED,
                "Feishu is disabled or missing Bitable configuration",
                retryable=False,
            )
        resolved_app = (app_token or self._config.bitable_app_token).strip()
        resolved_table = (table_id or self._config.service_case_table_id).strip()
        if not resolved_app or not resolved_table:
            raise FeishuIntegrationError(
                FeishuErrorCode.NOT_CONFIGURED,
                "Feishu is disabled or missing Bitable configuration",
                retryable=False,
            )
        return resolved_app, resolved_table

    def _records_path(self, app_token: str, table_id: str) -> str:
        return f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"

    def _record_path(self, app_token: str, table_id: str, record_id: str) -> str:
        return f"{self._records_path(app_token, table_id)}/{record_id}"

    def _parse_record(self, payload: dict[str, Any]) -> FeishuBitableRecord:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise FeishuIntegrationError(
                FeishuErrorCode.INVALID_RESPONSE,
                "Feishu Bitable response did not include data",
                retryable=False,
            )
        raw = data.get("record")
        if not isinstance(raw, dict):
            raw = data
        record_id = str(raw.get("record_id") or raw.get("id") or "").strip()
        if not record_id:
            raise FeishuIntegrationError(
                FeishuErrorCode.INVALID_RESPONSE,
                "Feishu Bitable response did not include record_id",
                retryable=False,
            )
        fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
        return FeishuBitableRecord(record_id=record_id, fields=fields)
