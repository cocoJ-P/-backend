from uuid import uuid4

from app.core.config import Settings
from app.core.database import SessionLocal
from app.core.time import utc_now
from app.domains.enterprise.enums import EnterpriseType
from app.domains.enterprise.models import Enterprise
from app.domains.enterprise.repository import add_enterprise
from app.domains.enterprise.seed import DEMO_ENTERPRISE_ID, seed_demo_enterprise
from app.domains.identity.enums import (
    EnterpriseMemberRole,
    EnterpriseMemberStatus,
    UserStatus,
)
from app.domains.identity.models import EnterpriseMember, User
from app.domains.identity.repository import create_membership, create_user
from app.domains.identity.seed import DEMO_USER_ID, seed_demo_identity


def _header(user_id) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user_id)}


def test_dev_identity_enabled_parses_false_string():
    parsed = Settings(DEV_IDENTITY_ENABLED="false")
    assert parsed.DEV_IDENTITY_ENABLED is False


def test_dev_identity_enabled_parses_true_string():
    parsed = Settings(DEV_IDENTITY_ENABLED="true")
    assert parsed.DEV_IDENTITY_ENABLED is True


def test_me_demo_identity(client):
    db = SessionLocal()
    try:
        seed_demo_identity(db)
    finally:
        db.close()

    response = client.get("/api/me", headers=_header(DEMO_USER_ID))
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == str(DEMO_USER_ID)
    assert payload["user"]["display_name"] == "Demo User"
    assert payload["user"]["status"] == "active"
    assert payload["enterprise"]["id"] == str(DEMO_ENTERPRISE_ID)
    assert payload["enterprise"]["name"] == "筑脉科技"
    assert payload["membership"]["role"] == "owner"
    assert payload["membership"]["status"] == "active"


def test_me_seed_is_idempotent(client):
    db = SessionLocal()
    try:
        first = seed_demo_identity(db)
        second = seed_demo_identity(db)
        assert first.id == second.id == DEMO_USER_ID
    finally:
        db.close()

    response = client.get("/api/me", headers=_header(DEMO_USER_ID))
    assert response.status_code == 200


def test_me_missing_header(client):
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "DEV_IDENTITY_REQUIRED"


def test_me_invalid_uuid(client):
    response = client.get("/api/me", headers=_header("abc"))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DEV_USER_ID"


def test_me_unknown_user(client):
    response = client.get("/api/me", headers=_header(uuid4()))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


def test_me_disabled_user(client):
    db = SessionLocal()
    try:
        user = User(
            display_name="Disabled",
            status=UserStatus.DISABLED.value,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        create_user(db, user)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    response = client.get("/api/me", headers=_header(user_id))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_DISABLED"


def test_me_no_membership(client):
    db = SessionLocal()
    try:
        user = User(
            display_name="No Member",
            status=UserStatus.ACTIVE.value,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        create_user(db, user)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    response = client.get("/api/me", headers=_header(user_id))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ENTERPRISE_MEMBERSHIP_NOT_FOUND"


def test_me_inactive_membership(client):
    db = SessionLocal()
    try:
        enterprise = seed_demo_enterprise(db)
        user = User(
            display_name="Inactive Member",
            status=UserStatus.ACTIVE.value,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        create_user(db, user)
        create_membership(
            db,
            EnterpriseMember(
                user_id=user.id,
                enterprise_id=enterprise.id,
                role=EnterpriseMemberRole.MEMBER.value,
                status=EnterpriseMemberStatus.INACTIVE.value,
                created_at=utc_now(),
                updated_at=utc_now(),
            ),
        )
        db.commit()
        user_id = user.id
    finally:
        db.close()

    response = client.get("/api/me", headers=_header(user_id))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ENTERPRISE_MEMBERSHIP_NOT_FOUND"


def test_me_multiple_active_memberships(client):
    db = SessionLocal()
    try:
        first = seed_demo_enterprise(db)
        second = Enterprise(
            name="第二家企业",
            enterprise_type=EnterpriseType.SME.value,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        add_enterprise(db, second)
        user = User(
            display_name="Multi Member",
            status=UserStatus.ACTIVE.value,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        create_user(db, user)
        for enterprise in (first, second):
            create_membership(
                db,
                EnterpriseMember(
                    user_id=user.id,
                    enterprise_id=enterprise.id,
                    role=EnterpriseMemberRole.MEMBER.value,
                    status=EnterpriseMemberStatus.ACTIVE.value,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                ),
            )
        db.commit()
        user_id = user.id
    finally:
        db.close()

    response = client.get("/api/me", headers=_header(user_id))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ENTERPRISE_CONTEXT_REQUIRED"


def test_me_dev_identity_disabled(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEV_IDENTITY_ENABLED", False)
    db = SessionLocal()
    try:
        seed_demo_identity(db)
    finally:
        db.close()

    response = client.get("/api/me", headers=_header(DEMO_USER_ID))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_ingest_does_not_require_identity(client):
    response = client.post(
        "/api/content/ingest",
        json={"content_type": "text", "content": "无需身份头即可接入的测试正文，长度足够。"},
    )
    assert response.status_code == 201


def test_openapi_includes_dev_user_header(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert "/api/me" in payload["paths"]
    parameters = payload["paths"]["/api/me"]["get"].get("parameters", [])
    header = next(item for item in parameters if item.get("name") == "X-Dev-User-Id")
    assert header["in"] == "header"
    assert "development-only" in header["description"].lower()
