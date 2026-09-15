"""Persistence for ServiceCaseFeishuBinding."""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.integrations.feishu.enums import FeishuBindingSyncStatus, FeishuEventReceiptStatus
from app.integrations.feishu.event_receipt import FeishuEventReceipt
from app.integrations.feishu.models import ServiceCaseFeishuBinding


def add_binding(db: Session, binding: ServiceCaseFeishuBinding) -> ServiceCaseFeishuBinding:
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


def save_binding(db: Session, binding: ServiceCaseFeishuBinding) -> ServiceCaseFeishuBinding:
    binding.updated_at = utc_now()
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


def get_by_service_case_id(db: Session, service_case_id: UUID) -> ServiceCaseFeishuBinding | None:
    statement = select(ServiceCaseFeishuBinding).where(
        ServiceCaseFeishuBinding.service_case_id == service_case_id
    )
    return db.scalars(statement).first()


def get_by_record_id(
    db: Session,
    *,
    bitable_app_token: str,
    table_id: str,
    record_id: str,
) -> ServiceCaseFeishuBinding | None:
    statement = select(ServiceCaseFeishuBinding).where(
        ServiceCaseFeishuBinding.bitable_app_token == bitable_app_token,
        ServiceCaseFeishuBinding.table_id == table_id,
        ServiceCaseFeishuBinding.record_id == record_id,
    )
    return db.scalars(statement).first()


def list_outbound_recovery_candidates(
    db: Session,
    *,
    stale_before,
    limit: int,
) -> list[ServiceCaseFeishuBinding]:
    statement = (
        select(ServiceCaseFeishuBinding)
        .where(
            or_(
                and_(
                    ServiceCaseFeishuBinding.sync_status == FeishuBindingSyncStatus.FAILED.value,
                    ServiceCaseFeishuBinding.last_error_retryable.is_(True),
                ),
                and_(
                    ServiceCaseFeishuBinding.sync_status == FeishuBindingSyncStatus.PENDING.value,
                    ServiceCaseFeishuBinding.updated_at < stale_before,
                ),
            )
        )
        .order_by(ServiceCaseFeishuBinding.updated_at.asc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def list_inbound_recovery_candidates(
    db: Session,
    *,
    stale_before,
    limit: int,
) -> list[FeishuEventReceipt]:
    statement = (
        select(FeishuEventReceipt)
        .where(
            or_(
                and_(
                    FeishuEventReceipt.status == FeishuEventReceiptStatus.FAILED.value,
                    FeishuEventReceipt.retryable.is_(True),
                ),
                and_(
                    FeishuEventReceipt.status == FeishuEventReceiptStatus.RECEIVED.value,
                    FeishuEventReceipt.received_at < stale_before,
                ),
            )
        )
        .order_by(FeishuEventReceipt.received_at.asc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def list_bindings_oldest_first(db: Session, *, limit: int) -> list[ServiceCaseFeishuBinding]:
    statement = (
        select(ServiceCaseFeishuBinding)
        .order_by(ServiceCaseFeishuBinding.updated_at.asc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())
