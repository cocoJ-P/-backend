"""ServiceCase → Feishu Bitable outbound sync.

Creates Binding(pending) after ServiceCase is already committed, then talks to
Feishu outside the business transaction. Never mutates ServiceCase.status.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.domains.enterprise.models import Enterprise
from app.domains.identity.models import User
from app.domains.service_case.models import ServiceCase
from app.domains.submission.models import UserSubmission
from app.integrations.feishu.config import FeishuConfig
from app.integrations.feishu.enums import FeishuBindingSyncStatus, FeishuErrorCode
from app.integrations.feishu.errors import (
    FeishuIntegrationError,
    is_ambiguous_create_error,
    is_bitable_record_not_found,
)
from app.integrations.feishu.models import ServiceCaseFeishuBinding
from app.integrations.feishu.service import FeishuBindingService, FeishuIntegration, create_feishu_integration
from app.integrations.feishu.service_case_mapper import (
    ServiceCaseFeishuProjection,
    case_id_equals_filter,
    map_service_case_to_bitable_fields,
)

logger = get_logger(__name__)


def load_service_case_projection(
    db: Session,
    service_case_id: UUID,
) -> ServiceCaseFeishuProjection | None:
    statement = (
        select(ServiceCase, Enterprise, User, UserSubmission)
        .join(Enterprise, Enterprise.id == ServiceCase.enterprise_id)
        .join(User, User.id == ServiceCase.created_by_user_id)
        .join(UserSubmission, UserSubmission.id == ServiceCase.submission_id)
        .where(ServiceCase.id == service_case_id)
    )
    row = db.execute(statement).first()
    if row is None:
        return None
    case, enterprise, user, submission = row
    return ServiceCaseFeishuProjection(
        title=case.title,
        service_case_id=case.id,
        enterprise_name=enterprise.name,
        created_by_display_name=user.display_name,
        origin_type=submission.origin_type,
        status=case.status,
        created_at=case.created_at,
        submission_id=submission.id,
    )


class ServiceCaseFeishuSyncService:
    def __init__(
        self,
        *,
        integration: FeishuIntegration | None = None,
        session_factory=SessionLocal,
        binding_service: FeishuBindingService | None = None,
    ) -> None:
        self._integration = integration
        self._session_factory = session_factory
        self._bindings = binding_service or FeishuBindingService()
        self.last_error: FeishuIntegrationError | None = None

    def sync_service_case(
        self,
        service_case_id: UUID,
        *,
        db: Session | None = None,
    ) -> ServiceCaseFeishuBinding | None:
        owns_session = db is None
        session = db if db is not None else self._session_factory()
        try:
            return self._sync(session, service_case_id)
        finally:
            if owns_session:
                session.close()

    def ensure_outbound_sync(self, service_case_id: UUID) -> ServiceCaseFeishuBinding:
        db = self._session_factory()
        try:
            case = db.get(ServiceCase, service_case_id)
            if case is None:
                raise FeishuIntegrationError(
                    FeishuErrorCode.MAPPING_FAILED,
                    "ServiceCase not found",
                    retryable=False,
                )
            config = self._config()
            if not config.is_bitable_configured():
                raise FeishuIntegrationError(
                    FeishuErrorCode.NOT_CONFIGURED,
                    "Feishu is disabled or missing Bitable configuration",
                    retryable=False,
                )
            self._ensure_pending_binding(db, service_case_id, config)
            binding = self._sync(db, service_case_id)
            if binding is None:
                raise FeishuIntegrationError(
                    FeishuErrorCode.REQUEST_FAILED,
                    "Feishu outbound sync did not return a binding",
                    retryable=False,
                )
            return binding
        finally:
            db.close()

    def _sync(self, db: Session, service_case_id: UUID) -> ServiceCaseFeishuBinding | None:
        binding = self._bindings.get_by_service_case_id(db, service_case_id)
        if binding is None:
            logger.info(
                "feishu outbound skipped service_case_id=%s reason=no_binding",
                service_case_id,
            )
            return None
        try:
            if (
                binding.sync_status == FeishuBindingSyncStatus.SYNCED.value
                and binding.record_id
            ):
                logger.info(
                    "feishu outbound already synced service_case_id=%s binding_id=%s record_id=%s",
                    service_case_id,
                    binding.id,
                    binding.record_id,
                )
                return binding
            if binding.record_id:
                return self._confirm_existing_record(db, binding)
            return self._reconcile_or_create(db, binding)
        except FeishuIntegrationError as exc:
            return self._mark_failed(db, binding, exc)
        except Exception:
            logger.exception(
                "feishu outbound crashed service_case_id=%s binding_id=%s",
                service_case_id,
                binding.id,
            )
        return self._bindings.mark_failed(
            db,
            binding,
            error_code=FeishuErrorCode.REQUEST_FAILED.value,
            error_message="unexpected Feishu outbound sync failure",
            retryable=False,
        )

    def _confirm_existing_record(
        self,
        db: Session,
        binding: ServiceCaseFeishuBinding,
    ) -> ServiceCaseFeishuBinding:
        record_id = binding.record_id
        assert record_id is not None
        try:
            self._bitable().get_record(
                record_id,
                app_token=binding.bitable_app_token,
                table_id=binding.table_id,
            )
        except FeishuIntegrationError as exc:
            if is_bitable_record_not_found(exc):
                return self._mark_failed(
                    db,
                    binding,
                    FeishuIntegrationError(
                        FeishuErrorCode.RECORD_NOT_FOUND,
                        "Bound Feishu record no longer exists",
                        retryable=False,
                        provider_code=exc.provider_code,
                    ),
                )
            raise
        return self._bindings.mark_synced(db, binding, record_id=record_id)

    def _reconcile_or_create(
        self,
        db: Session,
        binding: ServiceCaseFeishuBinding,
    ) -> ServiceCaseFeishuBinding:
        projection = self._load_projection(db, binding.service_case_id)
        if projection is None:
            raise FeishuIntegrationError(
                FeishuErrorCode.MAPPING_FAILED,
                "ServiceCase projection could not be loaded",
                retryable=False,
            )
        existing = self._search_by_case_id(binding, projection.service_case_id)
        if len(existing) > 1:
            raise FeishuIntegrationError(
                FeishuErrorCode.DUPLICATE_CASE_RECORDS,
                "发现多个相同 Case ID 的飞书记录",
                retryable=False,
            )
        if len(existing) == 1:
            return self._bindings.mark_synced(db, binding, record_id=existing[0].record_id)
        fields = map_service_case_to_bitable_fields(projection)
        try:
            created = self._bitable().create_record(
                fields,
                app_token=binding.bitable_app_token,
                table_id=binding.table_id,
            )
        except FeishuIntegrationError as exc:
            if is_ambiguous_create_error(exc):
                return self._reconcile_after_ambiguous_create(db, binding, projection, exc)
            raise
        return self._bindings.mark_synced(db, binding, record_id=created.record_id)

    def _reconcile_after_ambiguous_create(
        self,
        db: Session,
        binding: ServiceCaseFeishuBinding,
        projection: ServiceCaseFeishuProjection,
        create_error: FeishuIntegrationError,
    ) -> ServiceCaseFeishuBinding:
        try:
            existing = self._search_by_case_id(binding, projection.service_case_id)
        except FeishuIntegrationError as exc:
            logger.warning(
                "feishu outbound reconciliation failed service_case_id=%s binding_id=%s "
                "code=%s provider_code=%s message=%s",
                binding.service_case_id,
                binding.id,
                exc.code,
                exc.provider_code,
                exc.message,
            )
            return self._mark_failed(db, binding, create_error)
        if len(existing) == 1:
            return self._bindings.mark_synced(db, binding, record_id=existing[0].record_id)
        if len(existing) > 1:
            raise FeishuIntegrationError(
                FeishuErrorCode.DUPLICATE_CASE_RECORDS,
                "发现多个相同 Case ID 的飞书记录",
                retryable=False,
            )
        return self._mark_failed(db, binding, create_error)

    def _search_by_case_id(self, binding: ServiceCaseFeishuBinding, service_case_id: UUID):
        return self._bitable().search_records(
            filter=case_id_equals_filter(service_case_id),
            app_token=binding.bitable_app_token,
            table_id=binding.table_id,
        )

    def _load_projection(
        self,
        db: Session,
        service_case_id: UUID,
    ) -> ServiceCaseFeishuProjection | None:
        return load_service_case_projection(db, service_case_id)

    def _ensure_pending_binding(
        self,
        db: Session,
        service_case_id: UUID,
        config: FeishuConfig,
    ) -> ServiceCaseFeishuBinding:
        existing = self._bindings.get_by_service_case_id(db, service_case_id)
        if existing is not None:
            return existing
        try:
            return self._bindings.create_pending_binding(
                db,
                service_case_id=service_case_id,
                bitable_app_token=config.bitable_app_token,
                table_id=config.service_case_table_id,
            )
        except IntegrityError:
            db.rollback()
            existing = self._bindings.get_by_service_case_id(db, service_case_id)
            if existing is None:
                raise
            return existing

    def _mark_failed(
        self,
        db: Session,
        binding: ServiceCaseFeishuBinding,
        error: FeishuIntegrationError,
    ) -> ServiceCaseFeishuBinding:
        self.last_error = error
        logger.warning(
            "feishu outbound failed service_case_id=%s binding_id=%s "
            "code=%s provider_code=%s message=%s",
            binding.service_case_id,
            binding.id,
            error.code,
            error.provider_code,
            error.message,
        )
        return self._bindings.mark_failed(
            db,
            binding,
            error_code=str(error.code),
            error_message=error.message,
            retryable=bool(error.retryable),
        )

    def _config(self) -> FeishuConfig:
        if self._integration is not None:
            return self._integration.config
        return FeishuConfig.from_settings()

    def _bitable(self):
        return self._integration_or_create().bitable

    def _integration_or_create(self) -> FeishuIntegration:
        if self._integration is None:
            self._integration = create_feishu_integration()
        return self._integration


def schedule_service_case_feishu_sync(
    db: Session,
    service_case_id: UUID,
    background_tasks: BackgroundTasks,
) -> None:
    try:
        config = FeishuConfig.from_settings()
        if not config.enabled:
            return
        if not config.is_bitable_configured():
            logger.warning(
                "feishu outbound not configured service_case_id=%s code=%s",
                service_case_id,
                FeishuErrorCode.NOT_CONFIGURED.value,
            )
            return
        service = ServiceCaseFeishuSyncService()
        service._ensure_pending_binding(db, service_case_id, config)
        background_tasks.add_task(run_service_case_feishu_sync, service_case_id)
        logger.info(
            "feishu outbound queued service_case_id=%s sync_status=pending",
            service_case_id,
        )
    except Exception:
        logger.exception(
            "feishu outbound enqueue failed service_case_id=%s",
            service_case_id,
        )


def run_service_case_feishu_sync(service_case_id: UUID) -> None:
    try:
        ServiceCaseFeishuSyncService().sync_service_case(service_case_id)
    except Exception:
        logger.exception(
            "feishu outbound background task failed service_case_id=%s",
            service_case_id,
        )
