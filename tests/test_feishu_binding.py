"""ServiceCaseFeishuBinding persistence tests. No Feishu HTTP."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.core.time import utc_now
from app.domains.enterprise.seed import DEMO_ENTERPRISE_ID
from app.domains.identity.seed import DEMO_USER_ID, seed_demo_identity
from app.domains.service_case.models import ServiceCase
from app.domains.submission.models import UserSubmission
from app.integrations.feishu.enums import FeishuBindingSyncStatus, FeishuErrorCode
from app.integrations.feishu.models import ServiceCaseFeishuBinding
from app.integrations.feishu.service import FeishuBindingService
from tests.test_service_cases import _create_succeeded_submission, _header

APP_TOKEN = "bascn_binding_app"
TABLE_ID = "tbl_binding_table"


def _count_bindings() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(ServiceCaseFeishuBinding)) or 0)
    finally:
        db.close()


def _insert_service_case() -> UUID:
    db = SessionLocal()
    try:
        seed_demo_identity(db)
        now = utc_now()
        submission = UserSubmission(
            user_id=DEMO_USER_ID,
            enterprise_id=DEMO_ENTERPRISE_ID,
            input_type="text",
            input_content="事项",
            input_preview="事项",
            origin_type="user_input",
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.add(submission)
        db.flush()
        case = ServiceCase(
            enterprise_id=DEMO_ENTERPRISE_ID,
            created_by_user_id=DEMO_USER_ID,
            submission_id=submission.id,
            title="测试事项",
            status="open",
            created_at=now,
            updated_at=now,
        )
        db.add(case)
        db.commit()
        return case.id
    finally:
        db.close()


def test_create_pending_binding_defaults():
    case_id = _insert_service_case()
    db = SessionLocal()
    try:
        binding = FeishuBindingService().create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        assert binding.service_case_id == case_id
        assert binding.record_id is None
        assert binding.sync_status == FeishuBindingSyncStatus.PENDING.value
        assert binding.last_synced_at is None
        assert binding.last_error_code is None
        assert binding.last_error_message is None
        assert binding.bitable_app_token == APP_TOKEN
        assert binding.table_id == TABLE_ID
    finally:
        db.close()


def test_duplicate_binding_for_same_service_case_is_rejected():
    case_id = _insert_service_case()
    service = FeishuBindingService()
    db = SessionLocal()
    try:
        service.create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        with pytest.raises(IntegrityError):
            service.create_pending_binding(
                db,
                service_case_id=case_id,
                bitable_app_token=APP_TOKEN,
                table_id=TABLE_ID,
            )
    finally:
        db.rollback()
        db.close()


def test_same_feishu_record_cannot_be_bound_twice():
    first_case = _insert_service_case()
    second_case = _insert_service_case()
    service = FeishuBindingService()
    db = SessionLocal()
    try:
        first = service.create_pending_binding(
            db,
            service_case_id=first_case,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        service.mark_synced(db, first, record_id="recSHARED")
        second = service.create_pending_binding(
            db,
            service_case_id=second_case,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        with pytest.raises(IntegrityError):
            service.mark_synced(db, second, record_id="recSHARED")
    finally:
        db.rollback()
        db.close()


def test_mark_synced_sets_record_and_clears_errors():
    case_id = _insert_service_case()
    db = SessionLocal()
    try:
        service = FeishuBindingService()
        binding = service.create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        service.mark_failed(
            db,
            binding,
            error_code=FeishuErrorCode.TIMEOUT.value,
            error_message="temporary timeout",
        )
        synced = service.mark_synced(db, binding, record_id="recOK")
        assert synced.sync_status == FeishuBindingSyncStatus.SYNCED.value
        assert synced.record_id == "recOK"
        assert synced.last_synced_at is not None
        assert synced.last_error_code is None
        assert synced.last_error_message is None
    finally:
        db.close()


def test_mark_failed_stores_safe_error_fields():
    case_id = _insert_service_case()
    db = SessionLocal()
    try:
        service = FeishuBindingService()
        binding = service.create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        failed = service.mark_failed(
            db,
            binding,
            error_code=FeishuErrorCode.REQUEST_FAILED.value,
            error_message="provider failed",
        )
        assert failed.sync_status == FeishuBindingSyncStatus.FAILED.value
        assert failed.last_error_code == FeishuErrorCode.REQUEST_FAILED.value
        assert failed.last_error_message == "provider failed"
        assert failed.record_id is None
        assert failed.last_synced_at is None
    finally:
        db.close()


def test_mark_failed_keeps_existing_record_id():
    case_id = _insert_service_case()
    db = SessionLocal()
    try:
        service = FeishuBindingService()
        binding = service.create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        service.mark_synced(db, binding, record_id="recKEEP")
        failed = service.mark_failed(
            db,
            binding,
            error_code=FeishuErrorCode.TIMEOUT.value,
            error_message="update failed",
        )
        assert failed.sync_status == FeishuBindingSyncStatus.FAILED.value
        assert failed.record_id == "recKEEP"
        found = service.get_by_record_id(
            db,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
            record_id="recKEEP",
        )
        assert found is not None
        assert found.service_case_id == case_id
    finally:
        db.close()


def test_two_pending_bindings_allow_null_record_ids():
    first_case = _insert_service_case()
    second_case = _insert_service_case()
    service = FeishuBindingService()
    db = SessionLocal()
    try:
        first = service.create_pending_binding(
            db,
            service_case_id=first_case,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        second = service.create_pending_binding(
            db,
            service_case_id=second_case,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        assert first.record_id is None
        assert second.record_id is None
        assert first.sync_status == FeishuBindingSyncStatus.PENDING.value
        assert second.sync_status == FeishuBindingSyncStatus.PENDING.value
    finally:
        db.close()


def test_get_by_record_id_lookup():
    case_id = _insert_service_case()
    db = SessionLocal()
    try:
        service = FeishuBindingService()
        binding = service.create_pending_binding(
            db,
            service_case_id=case_id,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
        )
        service.mark_synced(db, binding, record_id="recLOOKUP")
        found = service.get_by_record_id(
            db,
            bitable_app_token=APP_TOKEN,
            table_id=TABLE_ID,
            record_id="recLOOKUP",
        )
        by_case = service.get_by_service_case_id(db, case_id)
        assert found is not None
        assert found.id == by_case.id
        assert found.record_id == "recLOOKUP"
    finally:
        db.close()


def test_create_service_case_does_not_create_binding_or_change_contract(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    response = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    case = body["service_case"]
    assert case["status"] == "open"
    assert "feishu_sync_status" not in case
    assert "feishu_record_id" not in case
    assert "feishu_table_id" not in case
    assert _count_bindings() == 0

    listed = client.get("/api/service-cases", headers=_header())
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert "feishu_sync_status" not in item
    assert "feishu_record_id" not in item

    mine = client.get("/api/service-cases/mine", headers=_header())
    assert mine.status_code == 200

    detail = client.get(f"/api/service-cases/{case['id']}", headers=_header())
    assert detail.status_code == 200
    assert "feishu_sync_status" not in detail.json()
    assert "feishu_record_id" not in detail.json()
