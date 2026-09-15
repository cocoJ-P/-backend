"""Generic Feishu Bitable operations via official lark-oapi. No ServiceCase mapping."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lark_oapi.api.bitable.v1 import (
    AppTableRecord,
    Condition,
    CreateAppTableRecordRequest,
    FilterInfo,
    GetAppTableRecordRequest,
    ListAppTableFieldRequest,
    SearchAppTableRecordRequest,
    SearchAppTableRecordRequestBody,
    UpdateAppTableRecordRequest,
)

from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError, is_bitable_record_not_found
from app.integrations.feishu.schemas import FeishuBitableRecord
from app.integrations.feishu.sdk import invoke_sdk


class FeishuBitableAdapter:
    def __init__(self, sdk_client: object | None, config: FeishuConfig) -> None:
        self._sdk = sdk_client
        self._config = config

    def create_record(
        self,
        fields: Mapping[str, Any],
        *,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> FeishuBitableRecord:
        app_token, table_id = self._resolve_table(app_token, table_id)
        request = (
            CreateAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .request_body(AppTableRecord.builder().fields(dict(fields)).build())
            .build()
        )
        response = invoke_sdk(
            lambda: self._record_api().create(request),
            secrets=self._secrets(),
        )
        return self._parse_single(response)

    def update_record(
        self,
        record_id: str,
        fields: Mapping[str, Any],
        *,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> FeishuBitableRecord:
        app_token, table_id = self._resolve_table(app_token, table_id)
        request = (
            UpdateAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .record_id(record_id)
            .request_body(AppTableRecord.builder().fields(dict(fields)).build())
            .build()
        )
        response = invoke_sdk(
            lambda: self._record_api().update(request),
            secrets=self._secrets(),
        )
        return self._parse_single(response)

    def get_record(
        self,
        record_id: str,
        *,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> FeishuBitableRecord:
        app_token, table_id = self._resolve_table(app_token, table_id)
        request = (
            GetAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .record_id(record_id)
            .build()
        )
        try:
            response = invoke_sdk(
                lambda: self._record_api().get(request),
                secrets=self._secrets(),
            )
        except FeishuIntegrationError as exc:
            if is_bitable_record_not_found(exc):
                raise FeishuIntegrationError(
                    FeishuErrorCode.RECORD_NOT_FOUND,
                    "Feishu Bitable record was not found",
                    retryable=False,
                    provider_code=exc.provider_code,
                    log_id=exc.log_id,
                ) from exc
            raise
        return self._parse_single(response)

    def search_records(
        self,
        *,
        filter: Mapping[str, Any] | None = None,
        page_size: int = 20,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> list[FeishuBitableRecord]:
        app_token, table_id = self._resolve_table(app_token, table_id)
        body = SearchAppTableRecordRequestBody.builder().automatic_fields(False)
        if filter is not None:
            body = body.filter(self._to_filter(filter))
        request = (
            SearchAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .page_size(page_size)
            .request_body(body.build())
            .build()
        )
        response = invoke_sdk(
            lambda: self._record_api().search(request),
            secrets=self._secrets(),
        )
        return self._parse_many(response)

    def list_fields(
        self,
        *,
        app_token: str | None = None,
        table_id: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        app_token, table_id = self._resolve_table(app_token, table_id)
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            builder = (
                ListAppTableFieldRequest.builder()
                .app_token(app_token)
                .table_id(table_id)
                .page_size(page_size)
            )
            if page_token:
                builder = builder.page_token(page_token)
            response = invoke_sdk(
                lambda request=builder.build(): self._field_api().list(request),
                secrets=self._secrets(),
            )
            data = getattr(response, "data", None)
            batch = getattr(data, "items", None) or []
            for raw in batch:
                items.append(
                    {
                        "field_name": getattr(raw, "field_name", None),
                        "field_id": getattr(raw, "field_id", None),
                        "type": getattr(raw, "type", None),
                    }
                )
            if not getattr(data, "has_more", False):
                break
            page_token = getattr(data, "page_token", None)
            if not page_token:
                break
        return items

    def _record_api(self):
        client = self._require_sdk()
        return client.bitable.v1.app_table_record

    def _field_api(self):
        client = self._require_sdk()
        return client.bitable.v1.app_table_field

    def _require_sdk(self):
        if self._sdk is None:
            raise FeishuIntegrationError(
                FeishuErrorCode.NOT_CONFIGURED,
                "Feishu is disabled or missing Bitable configuration",
                retryable=False,
            )
        return self._sdk

    def _resolve_table(self, app_token: str | None, table_id: str | None) -> tuple[str, str]:
        if not self._config.is_bitable_configured() and not (
            app_token and table_id and self._config.is_auth_configured()
        ):
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

    def _secrets(self) -> tuple[str, ...]:
        return tuple(item for item in (self._config.app_secret,) if item)

    def _to_filter(self, raw: Mapping[str, Any]) -> FilterInfo:
        conditions: list[Condition] = []
        for item in raw.get("conditions") or []:
            if not isinstance(item, Mapping):
                continue
            values = [str(value) for value in (item.get("value") or [])]
            conditions.append(
                Condition.builder()
                .field_name(str(item.get("field_name") or ""))
                .operator(str(item.get("operator") or "is"))
                .value(values)
                .build()
            )
        return (
            FilterInfo.builder()
            .conjunction(str(raw.get("conjunction") or "and"))
            .conditions(conditions)
            .build()
        )

    def _parse_single(self, response: object) -> FeishuBitableRecord:
        data = getattr(response, "data", None)
        raw = getattr(data, "record", None) if data is not None else None
        if raw is None:
            raw = data
        record_id = str(getattr(raw, "record_id", None) or getattr(raw, "id", None) or "").strip()
        if not record_id:
            raise FeishuIntegrationError(
                FeishuErrorCode.INVALID_RESPONSE,
                "Feishu Bitable response did not include record_id",
                retryable=False,
            )
        fields = getattr(raw, "fields", None)
        if not isinstance(fields, dict):
            fields = {}
        return FeishuBitableRecord(record_id=record_id, fields=fields)

    def _parse_many(self, response: object) -> list[FeishuBitableRecord]:
        data = getattr(response, "data", None)
        items = getattr(data, "items", None) if data is not None else None
        if items is None:
            return []
        records: list[FeishuBitableRecord] = []
        for raw in items:
            record_id = str(getattr(raw, "record_id", None) or getattr(raw, "id", None) or "").strip()
            if not record_id:
                raise FeishuIntegrationError(
                    FeishuErrorCode.INVALID_RESPONSE,
                    "Feishu Bitable search response did not include record_id",
                    retryable=False,
                )
            fields = getattr(raw, "fields", None)
            if not isinstance(fields, dict):
                fields = {}
            records.append(FeishuBitableRecord(record_id=record_id, fields=fields))
        return records
