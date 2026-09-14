"""Feishu integration entrypoints: HTTP adapter factory and binding state service.

Does not sync ServiceCase. Does not mutate ServiceCase.status.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.integrations.feishu.bitable import FeishuBitableAdapter
from app.integrations.feishu.client import FeishuClient
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuBindingSyncStatus
from app.integrations.feishu.errors import sanitize_feishu_text
from app.integrations.feishu.models import ServiceCaseFeishuBinding
from app.integrations.feishu.repository import (
    add_binding,
    get_by_record_id,
    get_by_service_case_id,
    save_binding,
)
from app.integrations.feishu.token_provider import FeishuTenantTokenProvider

_shared_http_client: httpx.Client | None = None


@dataclass
class FeishuIntegration:
    config: FeishuConfig
    token_provider: FeishuTenantTokenProvider
    client: FeishuClient
    bitable: FeishuBitableAdapter


FeishuAdapter = FeishuIntegration


def create_feishu_integration(
    *,
    config: FeishuConfig | None = None,
    http_client: httpx.Client | None = None,
) -> FeishuIntegration:
    resolved = config or FeishuConfig.from_settings()
    client_http = http_client or _shared_client(resolved)
    feishu_client = FeishuClient(client_http, resolved)
    token_provider = FeishuTenantTokenProvider(feishu_client, resolved)
    feishu_client.set_token_provider(token_provider)
    return FeishuIntegration(
        config=resolved,
        token_provider=token_provider,
        client=feishu_client,
        bitable=FeishuBitableAdapter(feishu_client, resolved),
    )


def _shared_client(config: FeishuConfig) -> httpx.Client:
    global _shared_http_client
    if _shared_http_client is None:
        _shared_http_client = httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout_seconds),
        )
    return _shared_http_client


def reset_shared_http_client() -> None:
    global _shared_http_client
    if _shared_http_client is not None:
        _shared_http_client.close()
        _shared_http_client = None


class FeishuBindingService:
    def create_pending_binding(
        self,
        db: Session,
        *,
        service_case_id: UUID,
        bitable_app_token: str,
        table_id: str,
    ) -> ServiceCaseFeishuBinding:
        now = utc_now()
        binding = ServiceCaseFeishuBinding(
            service_case_id=service_case_id,
            bitable_app_token=bitable_app_token,
            table_id=table_id,
            record_id=None,
            sync_status=FeishuBindingSyncStatus.PENDING.value,
            last_synced_at=None,
            last_error_code=None,
            last_error_message=None,
            created_at=now,
            updated_at=now,
        )
        return add_binding(db, binding)

    def get_by_service_case_id(
        self,
        db: Session,
        service_case_id: UUID,
    ) -> ServiceCaseFeishuBinding | None:
        return get_by_service_case_id(db, service_case_id)

    def get_by_record_id(
        self,
        db: Session,
        *,
        bitable_app_token: str,
        table_id: str,
        record_id: str,
    ) -> ServiceCaseFeishuBinding | None:
        return get_by_record_id(
            db,
            bitable_app_token=bitable_app_token,
            table_id=table_id,
            record_id=record_id,
        )

    def mark_synced(
        self,
        db: Session,
        binding: ServiceCaseFeishuBinding,
        *,
        record_id: str,
    ) -> ServiceCaseFeishuBinding:
        binding.sync_status = FeishuBindingSyncStatus.SYNCED.value
        binding.record_id = record_id
        binding.last_synced_at = utc_now()
        binding.last_error_code = None
        binding.last_error_message = None
        return save_binding(db, binding)

    def mark_failed(
        self,
        db: Session,
        binding: ServiceCaseFeishuBinding,
        *,
        error_code: str,
        error_message: str | None,
        secrets: tuple[str, ...] = (),
    ) -> ServiceCaseFeishuBinding:
        binding.sync_status = FeishuBindingSyncStatus.FAILED.value
        binding.last_error_code = (error_code or "")[:128] or None
        binding.last_error_message = sanitize_feishu_text(error_message or "", secrets) or None
        return save_binding(db, binding)
