"""Feishu sync retry and reconciliation. Does not mutate Domain from remote drift."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.service_case.models import ServiceCase
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import (
    FeishuBindingSyncStatus,
    FeishuErrorCode,
    FeishuEventReceiptStatus,
)
from app.integrations.feishu.errors import (
    FeishuIntegrationError,
    is_bitable_record_not_found,
)
from app.integrations.feishu.event_receipt import FeishuEventReceipt
from app.integrations.feishu.events.processor import FeishuEventProcessor
from app.integrations.feishu.models import ServiceCaseFeishuBinding
from app.integrations.feishu.outbound import (
    ServiceCaseFeishuSyncService,
    load_service_case_projection,
)
from app.integrations.feishu.repository import (
    list_bindings_oldest_first,
    list_inbound_recovery_candidates,
    list_outbound_recovery_candidates,
)
from app.integrations.feishu.schemas import FeishuBitableRecord
from app.integrations.feishu.service import FeishuBindingService, FeishuIntegration, create_feishu_integration
from app.integrations.feishu.service_case_mapper import (
    FIELD_STATUS,
    STATUS_LABELS,
    case_id_equals_filter,
    map_service_case_to_bitable_fields,
    normalize_single_select_value,
    read_remote_case_id,
)

logger = get_logger(__name__)

RESULT_SYNCED = "synced"
RESULT_ALREADY_SYNCED = "already_synced"
RESULT_FAILED = "failed"
RESULT_SKIPPED = "skipped"
RESULT_PROCESSED = "processed"
RESULT_REPAIRED = "repaired"
RESULT_ALREADY_CONSISTENT = "already_consistent"
ACTION_CREATED = "created"
ACTION_ADOPTED = "adopted"
ACTION_UPDATED = "updated"
ACTION_RECREATED = "recreated"
ACTION_STATUS_REPAIRED = "status_drift_repaired"
ACTION_OUTBOUND_SYNCED = "outbound_synced"
ACTION_NO_BINDING = "no_binding"


@dataclass
class OutboundRetryResult:
    result: str
    service_case_id: UUID
    binding_status: str | None
    record_id: str | None
    retry_count: int
    action: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class InboundRetryResult:
    result: str
    receipt_id: UUID
    receipt_status: str
    retry_count: int
    case_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class ReconcileResult:
    result: str
    action: str
    service_case_id: UUID
    binding_status: str | None
    remote: str
    remote_status: str | None
    record_id: str | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class BatchRetrySummary:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0


class FeishuSyncRecoveryService:
    def __init__(
        self,
        *,
        integration: FeishuIntegration | None = None,
        session_factory=SessionLocal,
        binding_service: FeishuBindingService | None = None,
        sync_service: ServiceCaseFeishuSyncService | None = None,
        processor: FeishuEventProcessor | None = None,
    ) -> None:
        self._integration = integration
        self._session_factory = session_factory
        self._bindings = binding_service or FeishuBindingService()
        self._sync = sync_service or ServiceCaseFeishuSyncService(
            integration=integration,
            session_factory=session_factory,
            binding_service=self._bindings,
        )
        self._processor = processor or FeishuEventProcessor(
            integration=integration,
            session_factory=session_factory,
            binding_service=self._bindings,
        )

    def retry_service_case_sync(self, service_case_id: UUID) -> OutboundRetryResult:
        snapshot = self._load_outbound_snapshot(service_case_id)
        if snapshot is None:
            return OutboundRetryResult(
                result=RESULT_FAILED,
                service_case_id=service_case_id,
                binding_status=None,
                record_id=None,
                retry_count=0,
                error_code=FeishuErrorCode.MAPPING_FAILED.value,
                error_message="ServiceCase not found",
            )
        binding, projection = snapshot
        if binding is None:
            return OutboundRetryResult(
                result=RESULT_FAILED,
                service_case_id=service_case_id,
                binding_status=None,
                record_id=None,
                retry_count=0,
                action=ACTION_NO_BINDING,
                error_code=FeishuErrorCode.MAPPING_FAILED.value,
                error_message="ServiceCase has no Feishu binding",
            )
        if binding.sync_status == FeishuBindingSyncStatus.SYNCED.value and binding.record_id:
            return OutboundRetryResult(
                result=RESULT_ALREADY_SYNCED,
                service_case_id=service_case_id,
                binding_status=binding.sync_status,
                record_id=binding.record_id,
                retry_count=int(binding.retry_count or 0),
                action=RESULT_ALREADY_SYNCED,
            )
        if projection is None:
            return OutboundRetryResult(
                result=RESULT_FAILED,
                service_case_id=service_case_id,
                binding_status=binding.sync_status,
                record_id=binding.record_id,
                retry_count=int(binding.retry_count or 0),
                error_code=FeishuErrorCode.MAPPING_FAILED.value,
                error_message="ServiceCase projection could not be loaded",
            )
        logger.info(
            "Feishu outbound retry started service_case_id=%s binding_id=%s record_id=%s",
            service_case_id,
            binding.id,
            binding.record_id or "-",
        )
        db = self._session_factory()
        try:
            current = self._bindings.get_by_service_case_id(db, service_case_id)
            if current is None:
                return OutboundRetryResult(
                    result=RESULT_FAILED,
                    service_case_id=service_case_id,
                    binding_status=None,
                    record_id=None,
                    retry_count=0,
                    error_code=FeishuErrorCode.MAPPING_FAILED.value,
                    error_message="ServiceCase has no Feishu binding",
                )
            current = self._bindings.note_retry_attempt(db, current)
            retry_count = int(current.retry_count or 0)
            binding_id = current.id
            record_id = current.record_id
            app_token = current.bitable_app_token
            table_id = current.table_id
        finally:
            db.close()
        try:
            remote, action = self._resolve_remote_record(
                service_case_id=service_case_id,
                projection=projection,
                record_id=record_id,
                app_token=app_token,
                table_id=table_id,
                restore_snapshot=True,
            )
            binding = self._persist_synced(binding_id, remote.record_id)
            if (
                binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
                and binding.record_id
                and binding.record_id != remote.record_id
            ):
                logger.info(
                    "Feishu outbound retry succeeded service_case_id=%s result=already_synced record_id=%s",
                    service_case_id,
                    binding.record_id,
                )
                return OutboundRetryResult(
                    result=RESULT_ALREADY_SYNCED,
                    service_case_id=service_case_id,
                    binding_status=binding.sync_status,
                    record_id=binding.record_id,
                    retry_count=retry_count,
                    action=RESULT_ALREADY_SYNCED,
                )
            logger.info(
                "Feishu outbound retry succeeded service_case_id=%s record_id=%s action=%s retry_count=%s",
                service_case_id,
                remote.record_id,
                action,
                retry_count,
            )
            return OutboundRetryResult(
                result=RESULT_SYNCED,
                service_case_id=service_case_id,
                binding_status=binding.sync_status,
                record_id=binding.record_id,
                retry_count=retry_count,
                action=action,
            )
        except FeishuIntegrationError as exc:
            binding = self._persist_failed(binding_id, exc)
            logger.warning(
                "Feishu outbound retry failed service_case_id=%s error_code=%s retry_count=%s",
                service_case_id,
                exc.code,
                retry_count,
            )
            return OutboundRetryResult(
                result=RESULT_FAILED,
                service_case_id=service_case_id,
                binding_status=binding.sync_status if binding is not None else None,
                record_id=binding.record_id if binding is not None else record_id,
                retry_count=retry_count,
                error_code=str(exc.code),
                error_message=exc.message,
            )

    def retry_event_receipt(self, receipt_id: UUID) -> InboundRetryResult:
        db = self._session_factory()
        try:
            receipt = db.get(FeishuEventReceipt, receipt_id)
            if receipt is None:
                return InboundRetryResult(
                    result=RESULT_FAILED,
                    receipt_id=receipt_id,
                    receipt_status="missing",
                    retry_count=0,
                    error_code=FeishuErrorCode.REQUEST_FAILED.value,
                    error_message="EventReceipt not found",
                )
            status = receipt.status
            retry_count = int(receipt.retry_count or 0)
            if status in {
                FeishuEventReceiptStatus.PROCESSED.value,
                FeishuEventReceiptStatus.IGNORED.value,
            }:
                return InboundRetryResult(
                    result=RESULT_SKIPPED,
                    receipt_id=receipt_id,
                    receipt_status=status,
                    retry_count=retry_count,
                )
        finally:
            db.close()
        logger.info("Feishu inbound retry started receipt_id=%s", receipt_id)
        try:
            receipt = self._processor.retry_receipt(receipt_id)
        except FeishuIntegrationError as exc:
            logger.warning(
                "Feishu inbound retry failed receipt_id=%s error_code=%s",
                receipt_id,
                exc.code,
            )
            return InboundRetryResult(
                result=RESULT_FAILED,
                receipt_id=receipt_id,
                receipt_status=FeishuEventReceiptStatus.FAILED.value,
                retry_count=retry_count + 1,
                error_code=str(exc.code),
                error_message=exc.message,
            )
        case_id = self._case_id_for_record(receipt.record_id, receipt.app_token, receipt.table_id)
        if receipt.status == FeishuEventReceiptStatus.PROCESSED.value:
            logger.info(
                "Feishu inbound retry processed receipt_id=%s event_id=%s case_id=%s retry_count=%s",
                receipt.id,
                receipt.event_id,
                case_id or "-",
                receipt.retry_count,
            )
            return InboundRetryResult(
                result=RESULT_PROCESSED,
                receipt_id=receipt.id,
                receipt_status=receipt.status,
                retry_count=int(receipt.retry_count or 0),
                case_id=case_id,
            )
        if receipt.status == FeishuEventReceiptStatus.IGNORED.value:
            return InboundRetryResult(
                result=RESULT_SKIPPED,
                receipt_id=receipt.id,
                receipt_status=receipt.status,
                retry_count=int(receipt.retry_count or 0),
                case_id=case_id,
                error_code=receipt.error_code,
            )
        logger.warning(
            "Feishu inbound retry failed receipt_id=%s error_code=%s retry_count=%s",
            receipt.id,
            receipt.error_code or "-",
            receipt.retry_count,
        )
        return InboundRetryResult(
            result=RESULT_FAILED,
            receipt_id=receipt.id,
            receipt_status=receipt.status,
            retry_count=int(receipt.retry_count or 0),
            case_id=case_id,
            error_code=receipt.error_code,
            error_message=receipt.error_message,
        )

    def reconcile_service_case(self, service_case_id: UUID) -> ReconcileResult:
        logger.info("Feishu reconciliation started service_case_id=%s", service_case_id)
        db = self._session_factory()
        try:
            case = db.get(ServiceCase, service_case_id)
            if case is None:
                return ReconcileResult(
                    result=RESULT_FAILED,
                    action=RESULT_FAILED,
                    service_case_id=service_case_id,
                    binding_status=None,
                    remote="-",
                    remote_status=None,
                    record_id=None,
                    error_code=FeishuErrorCode.MAPPING_FAILED.value,
                    error_message="ServiceCase not found",
                )
            backend_status = case.status
            binding = self._bindings.get_by_service_case_id(db, service_case_id)
            projection = load_service_case_projection(db, service_case_id)
            if binding is not None:
                db.expunge(binding)
        finally:
            db.close()
        if binding is None:
            try:
                synced = self._sync.ensure_outbound_sync(service_case_id)
            except FeishuIntegrationError as exc:
                return ReconcileResult(
                    result=RESULT_FAILED,
                    action=ACTION_OUTBOUND_SYNCED,
                    service_case_id=service_case_id,
                    binding_status=FeishuBindingSyncStatus.FAILED.value,
                    remote="missing",
                    remote_status=None,
                    record_id=None,
                    error_code=str(exc.code),
                    error_message=exc.message,
                )
            return ReconcileResult(
                result=RESULT_SYNCED,
                action=ACTION_OUTBOUND_SYNCED,
                service_case_id=service_case_id,
                binding_status=synced.sync_status,
                remote="exists" if synced.record_id else "missing",
                remote_status=STATUS_LABELS.get(backend_status),
                record_id=synced.record_id,
            )
        if projection is None:
            return ReconcileResult(
                result=RESULT_FAILED,
                action=RESULT_FAILED,
                service_case_id=service_case_id,
                binding_status=binding.sync_status,
                remote="-",
                remote_status=None,
                record_id=binding.record_id,
                error_code=FeishuErrorCode.MAPPING_FAILED.value,
                error_message="ServiceCase projection could not be loaded",
            )
        try:
            remote, action = self._resolve_remote_record(
                service_case_id=service_case_id,
                projection=projection,
                record_id=binding.record_id,
                app_token=binding.bitable_app_token,
                table_id=binding.table_id,
                restore_snapshot=False,
            )
            desired = STATUS_LABELS.get(backend_status)
            current_label = normalize_single_select_value(remote.fields.get(FIELD_STATUS))
            if desired and current_label != desired:
                self._bitable().update_record(
                    remote.record_id,
                    {FIELD_STATUS: desired},
                    app_token=binding.bitable_app_token,
                    table_id=binding.table_id,
                )
                logger.info(
                    "Feishu status drift repaired service_case_id=%s record_id=%s from_status=%s to_status=%s",
                    service_case_id,
                    remote.record_id,
                    current_label or "-",
                    desired,
                )
                persisted = self._persist_synced(
                    binding.id, remote.record_id, replace_synced=True
                )
                return ReconcileResult(
                    result=RESULT_REPAIRED,
                    action=ACTION_STATUS_REPAIRED,
                    service_case_id=service_case_id,
                    binding_status=persisted.sync_status,
                    remote="exists",
                    remote_status=desired,
                    record_id=persisted.record_id,
                )
            persisted = self._persist_synced(
                binding.id, remote.record_id, replace_synced=True
            )
            if action in {ACTION_CREATED, ACTION_RECREATED, ACTION_ADOPTED}:
                return ReconcileResult(
                    result=RESULT_REPAIRED,
                    action=action,
                    service_case_id=service_case_id,
                    binding_status=persisted.sync_status,
                    remote="exists",
                    remote_status=current_label,
                    record_id=persisted.record_id,
                )
            return ReconcileResult(
                result=RESULT_ALREADY_CONSISTENT,
                action=RESULT_ALREADY_CONSISTENT,
                service_case_id=service_case_id,
                binding_status=persisted.sync_status,
                remote="exists",
                remote_status=current_label,
                record_id=persisted.record_id,
            )
        except FeishuIntegrationError as exc:
            self._persist_failed(binding.id, exc)
            return ReconcileResult(
                result=RESULT_FAILED,
                action=RESULT_FAILED,
                service_case_id=service_case_id,
                binding_status=FeishuBindingSyncStatus.FAILED.value,
                remote="-",
                remote_status=None,
                record_id=binding.record_id,
                error_code=str(exc.code),
                error_message=exc.message,
            )

    def retry_failed_syncs(self, *, direction: str = "all", limit: int = 50) -> BatchRetrySummary:
        direction = (direction or "all").strip().lower()
        remaining = max(0, int(limit))
        summary = BatchRetrySummary()
        if direction in {"outbound", "all"} and remaining:
            outbound_ids = self._outbound_candidate_ids(remaining)
            for service_case_id in outbound_ids:
                summary.attempted += 1
                remaining -= 1
                try:
                    result = self.retry_service_case_sync(service_case_id)
                except Exception:
                    logger.exception(
                        "Feishu outbound retry failed service_case_id=%s",
                        service_case_id,
                    )
                    summary.failed += 1
                    continue
                if result.result in {RESULT_SYNCED, RESULT_ALREADY_SYNCED}:
                    summary.succeeded += 1
                elif result.result == RESULT_SKIPPED:
                    summary.skipped += 1
                else:
                    summary.failed += 1
        if direction in {"inbound", "all"} and remaining:
            inbound_ids = self._inbound_candidate_ids(remaining)
            for receipt_id in inbound_ids:
                summary.attempted += 1
                try:
                    result = self.retry_event_receipt(receipt_id)
                except Exception:
                    logger.exception("Feishu inbound retry failed receipt_id=%s", receipt_id)
                    summary.failed += 1
                    continue
                if result.result == RESULT_PROCESSED:
                    summary.succeeded += 1
                elif result.result == RESULT_SKIPPED:
                    summary.skipped += 1
                else:
                    summary.failed += 1
        return summary

    def reconcile_existing_bindings(self, *, limit: int = 50) -> BatchRetrySummary:
        summary = BatchRetrySummary()
        db = self._session_factory()
        try:
            bindings = list_bindings_oldest_first(db, limit=max(0, int(limit)))
            case_ids = [item.service_case_id for item in bindings]
        finally:
            db.close()
        for service_case_id in case_ids:
            summary.attempted += 1
            try:
                result = self.reconcile_service_case(service_case_id)
            except Exception:
                logger.exception(
                    "Feishu reconciliation failed service_case_id=%s",
                    service_case_id,
                )
                summary.failed += 1
                continue
            if result.result in {
                RESULT_ALREADY_CONSISTENT,
                RESULT_REPAIRED,
                RESULT_SYNCED,
                RESULT_ALREADY_SYNCED,
            }:
                summary.succeeded += 1
            else:
                summary.failed += 1
        return summary

    def _resolve_remote_record(
        self,
        *,
        service_case_id: UUID,
        projection,
        record_id: str | None,
        app_token: str,
        table_id: str,
        restore_snapshot: bool,
    ) -> tuple[FeishuBitableRecord, str]:
        expected = str(service_case_id)
        if record_id:
            remote = self._get_record_or_missing(record_id, app_token, table_id)
            if remote is not None:
                actual = read_remote_case_id(remote.fields)
                if actual != expected:
                    raise FeishuIntegrationError(
                        FeishuErrorCode.BINDING_RECORD_MISMATCH,
                        "Bound Feishu record Case ID does not match ServiceCase",
                        retryable=False,
                    )
                if restore_snapshot:
                    fields = map_service_case_to_bitable_fields(projection)
                    remote = self._bitable().update_record(
                        remote.record_id,
                        fields,
                        app_token=app_token,
                        table_id=table_id,
                    )
                return remote, ACTION_UPDATED
        matches = self._bitable().search_records(
            filter=case_id_equals_filter(service_case_id),
            app_token=app_token,
            table_id=table_id,
        )
        if len(matches) > 1:
            raise FeishuIntegrationError(
                FeishuErrorCode.DUPLICATE_CASE_RECORDS,
                "发现多个相同 Case ID 的飞书记录",
                retryable=False,
            )
        if len(matches) == 1:
            adopted = matches[0]
            actual = read_remote_case_id(adopted.fields)
            if actual is not None and actual != expected:
                raise FeishuIntegrationError(
                    FeishuErrorCode.BINDING_RECORD_MISMATCH,
                    "Bound Feishu record Case ID does not match ServiceCase",
                    retryable=False,
                )
            if restore_snapshot:
                fields = map_service_case_to_bitable_fields(projection)
                adopted = self._bitable().update_record(
                    adopted.record_id,
                    fields,
                    app_token=app_token,
                    table_id=table_id,
                )
            logger.info(
                "Feishu binding record adopted service_case_id=%s record_id=%s",
                service_case_id,
                adopted.record_id,
            )
            return adopted, ACTION_ADOPTED
        fields = map_service_case_to_bitable_fields(projection)
        created = self._bitable().create_record(fields, app_token=app_token, table_id=table_id)
        action = ACTION_RECREATED if record_id else ACTION_CREATED
        if action == ACTION_RECREATED:
            logger.info(
                "Feishu remote record recreated service_case_id=%s old_record_id=%s new_record_id=%s",
                service_case_id,
                record_id,
                created.record_id,
            )
        return created, action

    def _get_record_or_missing(
        self,
        record_id: str,
        app_token: str,
        table_id: str,
    ) -> FeishuBitableRecord | None:
        try:
            return self._bitable().get_record(record_id, app_token=app_token, table_id=table_id)
        except FeishuIntegrationError as exc:
            if is_bitable_record_not_found(exc):
                return None
            raise

    def _load_outbound_snapshot(self, service_case_id: UUID):
        db = self._session_factory()
        try:
            case = db.get(ServiceCase, service_case_id)
            if case is None:
                return None
            binding = self._bindings.get_by_service_case_id(db, service_case_id)
            projection = load_service_case_projection(db, service_case_id)
            if binding is not None:
                db.expunge(binding)
            return binding, projection
        finally:
            db.close()

    def _persist_synced(
        self,
        binding_id: UUID,
        record_id: str,
        *,
        replace_synced: bool = False,
    ) -> ServiceCaseFeishuBinding:
        db = self._session_factory()
        try:
            binding = db.get(ServiceCaseFeishuBinding, binding_id)
            assert binding is not None
            if (
                binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
                and binding.record_id
                and binding.record_id == record_id
            ):
                return binding
            if (
                binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
                and binding.record_id
                and not replace_synced
            ):
                return binding
            if binding.record_id and binding.record_id != record_id:
                binding = self._bindings.replace_record_id(db, binding, record_id)
            return self._bindings.mark_synced(db, binding, record_id=record_id)
        finally:
            db.close()

    def _persist_failed(
        self,
        binding_id: UUID,
        error: FeishuIntegrationError,
    ) -> ServiceCaseFeishuBinding | None:
        db = self._session_factory()
        try:
            binding = db.get(ServiceCaseFeishuBinding, binding_id)
            if binding is None:
                return None
            return self._bindings.mark_failed(
                db,
                binding,
                error_code=str(error.code),
                error_message=error.message,
                retryable=bool(error.retryable),
            )
        finally:
            db.close()

    def _outbound_candidate_ids(self, limit: int) -> list[UUID]:
        db = self._session_factory()
        try:
            stale_before = utc_now() - timedelta(seconds=self._stale_after_seconds())
            items = list_outbound_recovery_candidates(
                db, stale_before=stale_before, limit=limit
            )
            return [item.service_case_id for item in items]
        finally:
            db.close()

    def _inbound_candidate_ids(self, limit: int) -> list[UUID]:
        db = self._session_factory()
        try:
            stale_before = utc_now() - timedelta(seconds=self._stale_after_seconds())
            items = list_inbound_recovery_candidates(
                db, stale_before=stale_before, limit=limit
            )
            return [item.id for item in items]
        finally:
            db.close()

    def _case_id_for_record(
        self,
        record_id: str | None,
        app_token: str | None,
        table_id: str | None,
    ) -> UUID | None:
        if not record_id:
            return None
        config = self._config()
        db = self._session_factory()
        try:
            binding = self._bindings.get_by_record_id(
                db,
                bitable_app_token=app_token or config.bitable_app_token,
                table_id=table_id or config.service_case_table_id,
                record_id=record_id,
            )
            return None if binding is None else binding.service_case_id
        finally:
            db.close()

    def _stale_after_seconds(self) -> float:
        return float(self._config().sync_stale_after_seconds or 300)

    def _config(self) -> FeishuConfig:
        if self._integration is not None:
            return self._integration.config
        return FeishuConfig.from_settings()

    def _bitable(self):
        if self._integration is None:
            self._integration = create_feishu_integration()
        return self._integration.bitable
