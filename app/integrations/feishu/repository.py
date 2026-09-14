"""Persistence for ServiceCaseFeishuBinding."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
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
