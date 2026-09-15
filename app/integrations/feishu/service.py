"""Feishu integration entrypoints: SDK adapter factory and binding state service.

Does not mutate ServiceCase.status.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.integrations.feishu.bitable import FeishuBitableAdapter
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuBindingSyncStatus, FeishuErrorCode
from app.integrations.feishu.errors import FeishuIntegrationError, sanitize_feishu_text
from app.integrations.feishu.models import ServiceCaseFeishuBinding
from app.integrations.feishu.repository import (
    add_binding,
    get_by_record_id,
    get_by_service_case_id,
    save_binding,
)
from app.integrations.feishu.sdk import get_shared_sdk_client, reset_shared_sdk_client


@dataclass
class FeishuIntegration:
    config: FeishuConfig
    sdk_client: object | None
    bitable: FeishuBitableAdapter


FeishuAdapter = FeishuIntegration


def create_feishu_integration(
    *,
    config: FeishuConfig | None = None,
    sdk_client: object | None = None,
) -> FeishuIntegration:
    resolved = config or FeishuConfig.from_settings()
    client = sdk_client
    if client is None and resolved.is_auth_configured():
        client = get_shared_sdk_client(resolved)
    return FeishuIntegration(
        config=resolved,
        sdk_client=client,
        bitable=FeishuBitableAdapter(client, resolved),
    )


def reset_shared_feishu_clients() -> None:
    reset_shared_sdk_client()


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
            retry_count=0,
            last_retry_at=None,
            last_error_retryable=False,
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
        binding.last_error_retryable = False
        return save_binding(db, binding)

    def replace_record_id(
        self,
        db: Session,
        binding: ServiceCaseFeishuBinding,
        record_id: str,
    ) -> ServiceCaseFeishuBinding:
        binding.record_id = record_id
        try:
            return save_binding(db, binding)
        except IntegrityError as exc:
            db.rollback()
            raise FeishuIntegrationError(
                FeishuErrorCode.BINDING_RECORD_MISMATCH,
                "Feishu record_id is already bound to another ServiceCase",
                retryable=False,
            ) from exc

    def note_retry_attempt(
        self,
        db: Session,
        binding: ServiceCaseFeishuBinding,
    ) -> ServiceCaseFeishuBinding:
        binding.retry_count = int(binding.retry_count or 0) + 1
        binding.last_retry_at = utc_now()
        return save_binding(db, binding)

    def mark_failed(
        self,
        db: Session,
        binding: ServiceCaseFeishuBinding,
        *,
        error_code: str,
        error_message: str | None,
        secrets: tuple[str, ...] = (),
        retryable: bool = False,
    ) -> ServiceCaseFeishuBinding:
        binding.sync_status = FeishuBindingSyncStatus.FAILED.value
        binding.last_error_code = (error_code or "")[:128] or None
        binding.last_error_message = sanitize_feishu_text(error_message or "", secrets) or None
        binding.last_error_retryable = bool(retryable)
        return save_binding(db, binding)
