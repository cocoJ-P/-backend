"""Inbound Feishu event processing. Does not write back to Feishu."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.service_case.enums import ServiceCaseStatus
from app.domains.service_case.models import ServiceCase
from app.domains.service_case.service import transition_service_case_status
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuErrorCode, FeishuEventReceiptStatus
from app.integrations.feishu.errors import (
    FeishuIntegrationError,
    is_retryable_error_code,
    sanitize_feishu_text,
)
from app.integrations.feishu.event_receipt import FeishuEventReceipt
from app.integrations.feishu.events.parser import parse_bitable_record_changed_event
from app.integrations.feishu.events.schemas import (
    ACTION_RECORD_EDITED,
    BITABLE_RECORD_CHANGED_EVENT_TYPE,
    NormalizedBitableRecordChangedEvent,
)
from app.integrations.feishu.service import FeishuBindingService, FeishuIntegration, create_feishu_integration
from app.integrations.feishu.service_case_mapper import (
    FIELD_STATUS,
    map_bitable_status_label_to_service_case,
    normalize_single_select_value,
)

logger = get_logger(__name__)

UNMANAGED_RECORD_REASON = "FEISHU_UNMANAGED_RECORD"
IGNORE_OTHER_TABLE = "other_table"
IGNORE_OTHER_FIELD = "other_field"
IGNORE_UNMANAGED_RECORD = "unmanaged_record"
IGNORE_OTHER_BASE = "other_base"
IGNORE_OTHER_EVENT_TYPE = "other_event_type"


class FeishuEventProcessor:
    def __init__(
        self,
        *,
        integration: FeishuIntegration | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
        binding_service: FeishuBindingService | None = None,
        transition=transition_service_case_status,
    ) -> None:
        self._integration = integration
        self._session_factory = session_factory
        self._bindings = binding_service or FeishuBindingService()
        self._transition = transition

    def process_bitable_record_changed(self, data: object) -> FeishuEventReceipt | None:
        try:
            changes = parse_bitable_record_changed_event(data)
        except FeishuIntegrationError as exc:
            logger.warning(
                "feishu inbound parse failed code=%s provider_code=%s message=%s",
                exc.code,
                exc.provider_code,
                exc.message,
            )
            return None
        first = changes[0]
        self._log_received(changes)
        receipt = self._begin_receipt(first)
        if receipt is None:
            return None
        try:
            return self._process_changes(receipt, changes)
        except Exception:
            logger.exception(
                "Feishu event processing failed event_id=%s record_id=%s case_id=%s error_code=%s",
                receipt.event_id,
                receipt.record_id,
                None,
                FeishuErrorCode.REQUEST_FAILED.value,
            )
            return self._finish(
                receipt,
                FeishuEventReceiptStatus.FAILED,
                error_code=FeishuErrorCode.REQUEST_FAILED.value,
                error_message="unexpected Feishu inbound processing failure",
                retryable=False,
            )

    def retry_receipt(self, receipt_id: UUID) -> FeishuEventReceipt:
        db = self._session_factory()
        try:
            receipt = db.get(FeishuEventReceipt, receipt_id)
            if receipt is None:
                raise FeishuIntegrationError(
                    FeishuErrorCode.REQUEST_FAILED,
                    "EventReceipt not found",
                    retryable=False,
                )
            if receipt.status in {
                FeishuEventReceiptStatus.PROCESSED.value,
                FeishuEventReceiptStatus.IGNORED.value,
            }:
                db.expunge(receipt)
                return receipt
            if receipt.status not in {
                FeishuEventReceiptStatus.FAILED.value,
                FeishuEventReceiptStatus.RECEIVED.value,
            }:
                db.expunge(receipt)
                return receipt
            receipt.retry_count = int(receipt.retry_count or 0) + 1
            receipt.last_retry_at = utc_now()
            db.add(receipt)
            db.commit()
            db.refresh(receipt)
            event_id = receipt.event_id
            record_id = receipt.record_id
            app_token = receipt.app_token
            table_id = receipt.table_id
            event_type = receipt.event_type
            db.expunge(receipt)
        finally:
            db.close()

        if not record_id:
            failed = self._reload_receipt(event_id)
            return self._finish(
                failed,
                FeishuEventReceiptStatus.FAILED,
                error_code=FeishuErrorCode.INVALID_RESPONSE.value,
                error_message="EventReceipt has no record_id to retry",
                retryable=False,
            ) or failed

        config = self._config()
        change = NormalizedBitableRecordChangedEvent(
            event_id=event_id,
            event_type=event_type,
            app_token=app_token or config.bitable_app_token,
            table_id=table_id or config.service_case_table_id,
            record_id=record_id,
            action=ACTION_RECORD_EDITED,
        )
        if self._load_binding_meta(config, record_id) is None:
            current = self._reload_receipt(event_id)
            self._log_ignored(event_id, record_id, IGNORE_UNMANAGED_RECORD)
            return self._finish(
                current,
                FeishuEventReceiptStatus.IGNORED,
                error_code=UNMANAGED_RECORD_REASON,
                record_id=record_id,
            ) or current
        outcome = self._apply_status_change(change, config)
        if outcome == FeishuEventReceiptStatus.IGNORED.value:
            current = self._reload_receipt(event_id)
            self._log_ignored(event_id, record_id, IGNORE_UNMANAGED_RECORD)
            return self._finish(
                current,
                FeishuEventReceiptStatus.IGNORED,
                error_code=UNMANAGED_RECORD_REASON,
                record_id=record_id,
            ) or current
        return self._reload_receipt(event_id)

    def _process_changes(
        self,
        receipt: FeishuEventReceipt,
        changes: list[NormalizedBitableRecordChangedEvent],
    ) -> FeishuEventReceipt:
        config = self._config()
        first = changes[0]
        if first.event_type != BITABLE_RECORD_CHANGED_EVENT_TYPE:
            return self._ignore(receipt, first, IGNORE_OTHER_EVENT_TYPE)
        if first.app_token != config.bitable_app_token:
            return self._ignore(receipt, first, IGNORE_OTHER_BASE)
        if first.table_id != config.service_case_table_id:
            return self._ignore(receipt, first, IGNORE_OTHER_TABLE)

        candidates = [item for item in changes if self._is_status_edit_candidate(item, config)]
        if not candidates:
            return self._ignore(receipt, first, self._ignore_reason_for_changes(changes, config))

        results: list[str] = []
        last_record_id = candidates[0].record_id
        for change in candidates:
            last_record_id = change.record_id or last_record_id
            outcome = self._apply_status_change(change, config)
            results.append(outcome)
            if outcome == FeishuEventReceiptStatus.FAILED.value:
                return self._reload_receipt(first.event_id)
        receipt.record_id = last_record_id
        if FeishuEventReceiptStatus.FAILED.value in results:
            return receipt
        if FeishuEventReceiptStatus.PROCESSED.value in results:
            return self._finish(receipt, FeishuEventReceiptStatus.PROCESSED)
        unmanaged = results == [FeishuEventReceiptStatus.IGNORED.value]
        if unmanaged:
            self._log_ignored(first.event_id, last_record_id, IGNORE_UNMANAGED_RECORD)
        return self._finish(
            receipt,
            FeishuEventReceiptStatus.IGNORED,
            error_code=UNMANAGED_RECORD_REASON if unmanaged else None,
        )

    def _is_status_edit_candidate(
        self,
        change: NormalizedBitableRecordChangedEvent,
        config: FeishuConfig,
    ) -> bool:
        if change.action != ACTION_RECORD_EDITED:
            return False
        if not change.record_id:
            return False
        if change.has_changed_field_ids:
            return config.service_case_status_field_id in change.changed_field_ids
        return True

    def _apply_status_change(
        self,
        change: NormalizedBitableRecordChangedEvent,
        config: FeishuConfig,
    ) -> str:
        assert change.record_id is not None
        binding_meta = self._load_binding_meta(config, change.record_id)
        if binding_meta is None:
            return FeishuEventReceiptStatus.IGNORED.value
        service_case_id, _binding_id = binding_meta
        try:
            record = self._bitable().get_record(
                change.record_id,
                app_token=config.bitable_app_token,
                table_id=config.service_case_table_id,
            )
        except FeishuIntegrationError as exc:
            self._fail_receipt(
                change,
                error_code=str(exc.code),
                error_message=exc.message,
                case_id=service_case_id,
                retryable=bool(exc.retryable),
            )
            return FeishuEventReceiptStatus.FAILED.value

        label = self._read_status_label(record.fields, config)
        if not label:
            self._fail_receipt(
                change,
                error_code=FeishuErrorCode.UNSUPPORTED_SERVICE_CASE_STATUS.value,
                error_message="Feishu record did not include a service-case status value",
                case_id=service_case_id,
                retryable=False,
            )
            return FeishuEventReceiptStatus.FAILED.value
        try:
            target = ServiceCaseStatus(map_bitable_status_label_to_service_case(label))
        except FeishuIntegrationError as exc:
            self._fail_receipt(
                change,
                error_code=str(exc.code),
                error_message=exc.message,
                case_id=service_case_id,
                retryable=bool(exc.retryable),
            )
            return FeishuEventReceiptStatus.FAILED.value

        db = self._session_factory()
        try:
            receipt = self._get_receipt(db, change.event_id)
            case = db.get(ServiceCase, service_case_id)
            if case is None:
                self._mark(
                    db,
                    receipt,
                    FeishuEventReceiptStatus.IGNORED,
                    error_code=UNMANAGED_RECORD_REASON,
                    record_id=change.record_id,
                )
                return FeishuEventReceiptStatus.IGNORED.value
            current = ServiceCaseStatus(case.status)
            if current == target:
                logger.info(
                    "ServiceCase status already current case_id=%s status=%s",
                    case.id,
                    current.value,
                )
                self._mark(
                    db,
                    receipt,
                    FeishuEventReceiptStatus.PROCESSED,
                    record_id=change.record_id,
                )
                self._log_processed(change.event_id, case.id)
                return FeishuEventReceiptStatus.PROCESSED.value
            logger.info(
                "ServiceCase status transition case_id=%s record_id=%s from_status=%s to_status=%s",
                case.id,
                change.record_id,
                current.value,
                target.value,
            )
            try:
                self._transition(db, case, target)
            except AppException as exc:
                db.rollback()
                receipt = self._get_receipt(db, change.event_id)
                self._mark(
                    db,
                    receipt,
                    FeishuEventReceiptStatus.FAILED,
                    error_code=exc.code,
                    error_message=exc.message,
                    record_id=change.record_id,
                    retryable=False,
                )
                self._log_failed(
                    change.event_id,
                    change.record_id,
                    case.id,
                    exc.code,
                    exc.message,
                )
                return FeishuEventReceiptStatus.FAILED.value
            receipt = self._get_receipt(db, change.event_id)
            self._mark(
                db,
                receipt,
                FeishuEventReceiptStatus.PROCESSED,
                record_id=change.record_id,
            )
            self._log_processed(change.event_id, case.id)
            return FeishuEventReceiptStatus.PROCESSED.value
        finally:
            db.close()

    def _fail_receipt(
        self,
        change: NormalizedBitableRecordChangedEvent,
        *,
        error_code: str,
        error_message: str,
        case_id: object | None = None,
        retryable: bool | None = None,
    ) -> None:
        self._finish(
            self._reload_receipt(change.event_id),
            FeishuEventReceiptStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
            record_id=change.record_id,
            retryable=retryable,
        )
        self._log_failed(
            change.event_id,
            change.record_id,
            case_id,
            error_code,
            error_message,
        )

    def _ignore(
        self,
        receipt: FeishuEventReceipt,
        change: NormalizedBitableRecordChangedEvent,
        reason: str,
    ) -> FeishuEventReceipt | None:
        self._log_ignored(change.event_id, change.record_id, reason)
        return self._finish(receipt, FeishuEventReceiptStatus.IGNORED)

    def _ignore_reason_for_changes(
        self,
        changes: list[NormalizedBitableRecordChangedEvent],
        config: FeishuConfig,
    ) -> str:
        first = changes[0]
        if first.action and first.action != ACTION_RECORD_EDITED:
            return first.action
        if first.has_changed_field_ids and config.service_case_status_field_id not in first.changed_field_ids:
            return IGNORE_OTHER_FIELD
        return IGNORE_OTHER_FIELD

    def _log_received(self, changes: list[NormalizedBitableRecordChangedEvent]) -> None:
        for change in changes:
            logger.info(
                "Feishu event received event_id=%s record_id=%s action=%s",
                change.event_id,
                change.record_id or "-",
                change.action or "-",
            )

    def _log_ignored(self, event_id: str, record_id: object | None, reason: str) -> None:
        logger.info(
            "Feishu event ignored event_id=%s record_id=%s reason=%s",
            event_id,
            record_id or "-",
            reason,
        )

    def _log_processed(self, event_id: str, case_id: object) -> None:
        logger.info(
            "Feishu event processed event_id=%s case_id=%s receipt_status=processed",
            event_id,
            case_id,
        )

    def _log_failed(
        self,
        event_id: str,
        record_id: object | None,
        case_id: object | None,
        error_code: object,
        error_message: str | None = None,
    ) -> None:
        logger.warning(
            "Feishu event processing failed event_id=%s record_id=%s case_id=%s error_code=%s message=%s",
            event_id,
            record_id or "-",
            case_id if case_id is not None else "-",
            error_code,
            sanitize_feishu_text(error_message or "") or "-",
        )

    def _load_binding_meta(self, config: FeishuConfig, record_id: str) -> tuple[object, object] | None:
        db = self._session_factory()
        try:
            binding = self._bindings.get_by_record_id(
                db,
                bitable_app_token=config.bitable_app_token,
                table_id=config.service_case_table_id,
                record_id=record_id,
            )
            if binding is None:
                return None
            return binding.service_case_id, binding.id
        finally:
            db.close()

    def _read_status_label(self, fields: dict, config: FeishuConfig) -> str | None:
        raw = fields.get(FIELD_STATUS)
        if raw is None and config.service_case_status_field_id:
            raw = fields.get(config.service_case_status_field_id)
        return normalize_single_select_value(raw)

    def _begin_receipt(self, change: NormalizedBitableRecordChangedEvent) -> FeishuEventReceipt | None:
        db = self._session_factory()
        try:
            existing = self._get_receipt(db, change.event_id)
            if existing is not None:
                logger.info(
                    "feishu inbound duplicate event_id=%s status=%s",
                    existing.event_id,
                    existing.status,
                )
                return None
            receipt = FeishuEventReceipt(
                event_id=change.event_id,
                event_type=change.event_type,
                app_token=change.app_token,
                table_id=change.table_id,
                record_id=change.record_id,
                status=FeishuEventReceiptStatus.RECEIVED.value,
                received_at=utc_now(),
            )
            db.add(receipt)
            db.commit()
            db.refresh(receipt)
            return receipt
        except IntegrityError:
            db.rollback()
            logger.info("feishu inbound duplicate event_id=%s concurrent", change.event_id)
            return None
        finally:
            db.close()

    def _finish(
        self,
        receipt: FeishuEventReceipt | None,
        status: FeishuEventReceiptStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        record_id: str | None = None,
        retryable: bool | None = None,
    ) -> FeishuEventReceipt | None:
        if receipt is None:
            return None
        db = self._session_factory()
        try:
            current = self._get_receipt(db, receipt.event_id)
            if current is None:
                return receipt
            self._mark(
                db,
                current,
                status,
                error_code=error_code,
                error_message=error_message,
                record_id=record_id or receipt.record_id,
                retryable=retryable,
            )
            return current
        finally:
            db.close()

    def _reload_receipt(self, event_id: str) -> FeishuEventReceipt:
        db = self._session_factory()
        try:
            receipt = self._get_receipt(db, event_id)
            assert receipt is not None
            db.expunge(receipt)
            return receipt
        finally:
            db.close()

    def _mark(
        self,
        db: Session,
        receipt: FeishuEventReceipt,
        status: FeishuEventReceiptStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        record_id: str | None = None,
        retryable: bool | None = None,
    ) -> FeishuEventReceipt:
        receipt.status = status.value
        receipt.record_id = record_id if record_id is not None else receipt.record_id
        receipt.error_code = (error_code or "")[:128] or None
        receipt.error_message = sanitize_feishu_text(error_message or "") or None
        receipt.processed_at = utc_now() if status != FeishuEventReceiptStatus.RECEIVED else None
        if status == FeishuEventReceiptStatus.FAILED:
            receipt.retryable = (
                bool(retryable) if retryable is not None else is_retryable_error_code(error_code)
            )
        elif status in {FeishuEventReceiptStatus.PROCESSED, FeishuEventReceiptStatus.IGNORED}:
            receipt.retryable = False
        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        return receipt

    def _get_receipt(self, db: Session, event_id: str) -> FeishuEventReceipt | None:
        from sqlalchemy import select

        return db.scalars(
            select(FeishuEventReceipt).where(FeishuEventReceipt.event_id == event_id)
        ).first()

    def _config(self) -> FeishuConfig:
        if self._integration is not None:
            return self._integration.config
        return FeishuConfig.from_settings()

    def _bitable(self):
        if self._integration is None:
            self._integration = create_feishu_integration()
        return self._integration.bitable
