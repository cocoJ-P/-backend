from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.time import utc_now
from app.domains.discovery.models import DiscoveryItem
from app.domains.discovery.user_state_models import DiscoveryUserState
from app.domains.enterprise.enums import EnterpriseType
from app.domains.enterprise.models import Enterprise
from app.domains.enterprise.repository import add_enterprise
from app.domains.enterprise.seed import DEMO_ENTERPRISE_ID
from app.domains.identity.enums import (
    EnterpriseMemberRole,
    EnterpriseMemberStatus,
    UserStatus,
)
from app.domains.identity.models import EnterpriseMember, User
from app.domains.identity.repository import create_membership, create_user
from app.domains.identity.seed import DEMO_USER_ID, seed_demo_identity
from app.domains.opportunity.seed import DEMO_POLICY_ID, seed_demo_opportunities
from app.domains.submission.enums import SubmissionOriginType, SubmissionStatus
from app.domains.submission.models import UserSubmission
from app.integrations.llm.providers.fake import FakeLLMProvider
from tests.test_submissions import NOTICE, _success_payload, _use_fake_llm


def _header(user_id=DEMO_USER_ID) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user_id)}


def _seed_demo() -> None:
    db = SessionLocal()
    try:
        seed_demo_identity(db)
        seed_demo_opportunities(db)
    finally:
        db.close()


def _seed_peer_user(display_name: str = "Peer User") -> UUID:
    db = SessionLocal()
    try:
        seed_demo_identity(db)
        now = utc_now()
        user = User(
            display_name=display_name,
            status=UserStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        create_user(db, user)
        create_membership(
            db,
            EnterpriseMember(
                user_id=user.id,
                enterprise_id=DEMO_ENTERPRISE_ID,
                role=EnterpriseMemberRole.MEMBER.value,
                status=EnterpriseMemberStatus.ACTIVE.value,
                created_at=now,
                updated_at=now,
            ),
        )
        db.commit()
        return user.id
    finally:
        db.close()


def _seed_other_enterprise_user() -> UUID:
    db = SessionLocal()
    try:
        now = utc_now()
        enterprise = Enterprise(
            name="另一家企业",
            enterprise_type=EnterpriseType.SME.value,
            created_at=now,
            updated_at=now,
        )
        add_enterprise(db, enterprise)
        user = User(
            display_name="User B",
            status=UserStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        create_user(db, user)
        create_membership(
            db,
            EnterpriseMember(
                user_id=user.id,
                enterprise_id=enterprise.id,
                role=EnterpriseMemberRole.MEMBER.value,
                status=EnterpriseMemberStatus.ACTIVE.value,
                created_at=now,
                updated_at=now,
            ),
        )
        db.commit()
        return user.id
    finally:
        db.close()


def _create_manual(client, **overrides) -> dict:
    _seed_demo()
    payload = {
        "reference_type": "manual",
        "title": "人工智能企业产业对接活动",
        "summary": "面向成长阶段科技企业开放",
        "reason": "与你当前业务方向相关",
        "priority": "normal",
    }
    payload.update(overrides)
    response = client.post("/api/discoveries", headers=_header(), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_opportunity_discovery(client) -> dict:
    _seed_demo()
    response = client.post(
        "/api/discoveries",
        headers=_header(),
        json={
            "reference_type": "opportunity",
            "opportunity_id": str(DEMO_POLICY_ID),
            "reason": "与你当前的 AI 研发方向高度相关",
            "priority": "high",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _count_submissions() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(UserSubmission)) or 0)
    finally:
        db.close()


def _get_submission(submission_id: str) -> UserSubmission:
    db = SessionLocal()
    try:
        row = db.get(UserSubmission, UUID(submission_id))
        assert row is not None
        db.expunge(row)
        return row
    finally:
        db.close()


def _get_state(discovery_id: str, user_id=DEMO_USER_ID) -> DiscoveryUserState | None:
    db = SessionLocal()
    try:
        row = db.scalars(
            select(DiscoveryUserState).where(
                DiscoveryUserState.discovery_id == UUID(discovery_id),
                DiscoveryUserState.user_id == user_id,
            )
        ).first()
        if row is not None:
            db.expunge(row)
        return row
    finally:
        db.close()


def test_accept_discovery_saves_and_creates_pending_submission(client):
    item = _create_manual(client)
    response = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert body["user_state"]["disposition"] == "saved"
    assert body["user_state"]["discovery_id"] == item["id"]
    assert body["user_state"]["user_id"] == str(DEMO_USER_ID)
    submission = body["submission"]
    assert submission["status"] == "pending"
    assert submission["origin_type"] == "discovery"
    assert submission["origin_discovery_id"] == item["id"]
    assert submission["user"]["id"] == str(DEMO_USER_ID)

    stored = _get_submission(submission["id"])
    assert stored.origin_type == SubmissionOriginType.DISCOVERY.value
    assert stored.origin_discovery_id == UUID(item["id"])
    assert stored.status == SubmissionStatus.PENDING.value
    assert stored.intelligence_run_id is None
    state = _get_state(item["id"])
    assert state is not None
    assert state.disposition == "saved"
    assert state.seen_at is not None


def test_accept_reference_url_maps_to_url_input(client):
    item = _create_opportunity_discovery(client)
    assert item["reference_url"] == "https://example.beijing.gov.cn/rd-innovation-support"
    response = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert response.status_code == 201, response.text
    submission = response.json()["submission"]
    assert submission["input_type"] == "url"
    stored = _get_submission(submission["id"])
    assert stored.input_type == "url"
    assert stored.input_content == item["reference_url"]
    assert stored.origin_type == "discovery"


def test_accept_text_fallback_uses_snapshot_without_reason(client):
    item = _create_manual(client)
    assert item["reference_url"] is None
    response = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert response.status_code == 201, response.text
    submission = response.json()["submission"]
    assert submission["input_type"] == "text"
    stored = _get_submission(submission["id"])
    assert stored.input_type == "text"
    assert item["title"] in stored.input_content
    assert item["summary"] in stored.input_content
    assert "与你当前业务方向相关" not in stored.input_content
    assert "reason" not in stored.input_content.lower()


def test_accept_title_only_is_allowed(client):
    item = _create_manual(client, title="仅标题发现", summary=None, reason="不要进入正文")
    response = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert response.status_code == 201, response.text
    stored = _get_submission(response.json()["submission"]["id"])
    assert stored.input_type == "text"
    assert stored.input_content == "仅标题发现"
    assert "不要进入正文" not in stored.input_content


def test_accept_is_idempotent_for_same_user(client):
    item = _create_manual(client)
    first = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert first.status_code == 201, first.text
    submission_id = first.json()["submission"]["id"]
    before = _count_submissions()

    second = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["created"] is False
    assert body["submission"]["id"] == submission_id
    assert body["user_state"]["disposition"] == "saved"
    assert _count_submissions() == before


def test_two_users_accept_same_discovery_create_two_submissions(client):
    item = _create_manual(client)
    peer_id = _seed_peer_user()
    first = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    second = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header(peer_id))
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["submission"]["id"] != second.json()["submission"]["id"]
    assert _count_submissions() == 2
    assert _get_state(item["id"]).disposition == "saved"
    assert _get_state(item["id"], peer_id).disposition == "saved"


def test_accept_hides_other_enterprise_discovery(client):
    item = _create_manual(client)
    other_user_id = _seed_other_enterprise_user()
    response = client.post(
        f"/api/discoveries/{item['id']}/accept",
        headers=_header(other_user_id),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DISCOVERY_NOT_FOUND"
    assert _count_submissions() == 0


def test_accept_from_deprioritized_becomes_saved_and_creates_submission(client):
    item = _create_manual(client)
    patched = client.patch(
        f"/api/discoveries/{item['id']}/user-state",
        headers=_header(),
        json={"disposition": "deprioritized"},
    )
    assert patched.status_code == 200
    assert patched.json()["disposition"] == "deprioritized"

    response = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert response.status_code == 201, response.text
    assert response.json()["user_state"]["disposition"] == "saved"
    stored = _get_submission(response.json()["submission"]["id"])
    assert stored.origin_type == "discovery"
    assert stored.origin_discovery_id == UUID(item["id"])
    assert _get_state(item["id"]).disposition == "saved"


def test_process_discovery_origin_submission_uses_existing_pipeline(client, monkeypatch):
    item = _create_manual(
        client,
        title="2026年度科技创新项目",
        summary=NOTICE.strip(),
        reason="推荐理由不能进入解析",
    )
    accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert accepted.status_code == 201, accepted.text
    submission_id = accepted.json()["submission"]["id"]
    stored = _get_submission(submission_id)
    assert stored.status == "pending"
    assert stored.intelligence_run_id is None

    _use_fake_llm(monkeypatch, FakeLLMProvider(_success_payload(NOTICE)))
    processed = client.post(
        f"/api/user-submissions/{submission_id}/process",
        headers=_header(),
    )
    assert processed.status_code == 200, processed.text
    submission = processed.json()["submission"]
    assert submission["status"] == "succeeded"
    assert submission["origin_type"] == "discovery"
    assert submission["origin_discovery_id"] == item["id"]
    assert submission["intelligence_run_id"]
    assert processed.json()["intelligence"]["result"]["opportunity_claim"]["claimed_title"] == "2026年度科技创新项目"
    assert "推荐理由不能进入解析" not in submission["input_content"]


def test_mine_is_current_user_scoped(client):
    item = _create_manual(client)
    peer_id = _seed_peer_user()
    own_accept = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    peer_accept = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header(peer_id))
    assert own_accept.status_code == 201
    assert peer_accept.status_code == 201

    mine = client.get("/api/user-submissions/mine", headers=_header())
    assert mine.status_code == 200
    items = mine.json()["items"]
    assert [row["id"] for row in items] == [own_accept.json()["submission"]["id"]]
    assert items[0]["origin_type"] == "discovery"
    assert items[0]["origin_discovery_id"] == item["id"]
    assert "input_content" not in items[0]
    assert "intelligence" not in items[0]

    peer_mine = client.get("/api/user-submissions/mine", headers=_header(peer_id))
    assert [row["id"] for row in peer_mine.json()["items"]] == [peer_accept.json()["submission"]["id"]]


def test_enterprise_inventory_is_not_user_scoped(client):
    item = _create_manual(client)
    peer_id = _seed_peer_user()
    first = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    second = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header(peer_id))
    inventory = client.get("/api/user-submissions", headers=_header())
    assert inventory.status_code == 200
    ids = {row["id"] for row in inventory.json()["items"]}
    assert first.json()["submission"]["id"] in ids
    assert second.json()["submission"]["id"] in ids
    mine = client.get("/api/user-submissions/mine", headers=_header())
    assert [row["id"] for row in mine.json()["items"]] == [first.json()["submission"]["id"]]


def test_mine_contains_both_origins_newest_first(client):
    item = _create_manual(client)
    typed = client.post(
        "/api/user-submissions",
        headers=_header(),
        json={"input_type": "text", "content": "用户自己粘贴的申报通知正文。"},
    )
    assert typed.status_code == 201, typed.text
    accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert accepted.status_code == 201, accepted.text

    db = SessionLocal()
    try:
        base = utc_now()
        typed_row = db.get(UserSubmission, UUID(typed.json()["id"]))
        accepted_row = db.get(UserSubmission, UUID(accepted.json()["submission"]["id"]))
        assert typed_row is not None
        assert accepted_row is not None
        typed_row.created_at = base
        accepted_row.created_at = base + timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    mine = client.get("/api/user-submissions/mine", headers=_header())
    assert mine.status_code == 200
    items = mine.json()["items"]
    assert len(items) == 2
    assert items[0]["id"] == accepted.json()["submission"]["id"]
    assert items[0]["origin_type"] == "discovery"
    assert items[1]["id"] == typed.json()["id"]
    assert items[1]["origin_type"] == "user_input"
    assert items[1]["origin_discovery_id"] is None

    pending = client.get("/api/user-submissions/mine?status=pending", headers=_header())
    assert len(pending.json()["items"]) == 2
    failed = client.get("/api/user-submissions/mine?status=failed", headers=_header())
    assert failed.json()["items"] == []


def test_saved_collection_remains_independent_of_accept(client):
    item = _create_manual(client)
    patched = client.patch(
        f"/api/discoveries/{item['id']}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    assert patched.status_code == 200
    assert _count_submissions() == 0
    saved = client.get("/api/discoveries/saved", headers=_header())
    assert item["id"] in [row["id"] for row in saved.json()["items"]]
    mine = client.get("/api/user-submissions/mine", headers=_header())
    assert mine.json()["items"] == []

    accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert accepted.status_code == 201
    saved_after = client.get("/api/discoveries/saved", headers=_header())
    assert item["id"] in [row["id"] for row in saved_after.json()["items"]]
    mine_after = client.get("/api/user-submissions/mine", headers=_header())
    assert [row["id"] for row in mine_after.json()["items"]] == [accepted.json()["submission"]["id"]]


def test_accept_and_mine_require_identity(client):
    item = _create_manual(client)
    accept = client.post(f"/api/discoveries/{item['id']}/accept")
    assert accept.status_code == 401
    assert accept.json()["error"]["code"] == "DEV_IDENTITY_REQUIRED"
    mine = client.get("/api/user-submissions/mine")
    assert mine.status_code == 401
    assert mine.json()["error"]["code"] == "DEV_IDENTITY_REQUIRED"


def test_accept_missing_discovery_is_not_found(client):
    _seed_demo()
    response = client.post(f"/api/discoveries/{uuid4()}/accept", headers=_header())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DISCOVERY_NOT_FOUND"


def test_accept_withdrawn_discovery_is_rejected_without_side_effects(client):
    item = _create_manual(client)
    withdraw = client.post(f"/api/discoveries/{item['id']}/withdraw", headers=_header())
    assert withdraw.status_code == 200
    assert withdraw.json()["status"] == "withdrawn"
    assert _get_state(item["id"]) is None
    assert _count_submissions() == 0

    response = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DISCOVERY_NOT_ACTIVE"
    assert _get_state(item["id"]) is None
    assert _count_submissions() == 0


def test_accept_after_successful_accept_then_withdraw_keeps_original_submission(client):
    item = _create_manual(client)
    first = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert first.status_code == 201, first.text
    submission_id = first.json()["submission"]["id"]
    assert _get_state(item["id"]).disposition == "saved"
    withdraw = client.post(f"/api/discoveries/{item['id']}/withdraw", headers=_header())
    assert withdraw.status_code == 200
    assert withdraw.json()["status"] == "withdrawn"

    second = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DISCOVERY_NOT_ACTIVE"
    assert _count_submissions() == 1
    stored = _get_submission(submission_id)
    assert stored.status == SubmissionStatus.PENDING.value
    assert stored.origin_type == SubmissionOriginType.DISCOVERY.value
    assert stored.origin_discovery_id == UUID(item["id"])
    assert _get_state(item["id"]).disposition == "saved"


def test_openapi_accept_and_mine_require_dev_identity(client):
    payload = client.get("/openapi.json").json()
    paths = payload["paths"]
    expected = {
        "/api/discoveries/{discovery_id}/accept": ["post"],
        "/api/user-submissions/mine": ["get"],
    }
    for path, methods in expected.items():
        assert path in paths, path
        for method in methods:
            parameters = paths[path][method].get("parameters", [])
            header = next(item for item in parameters if item.get("name") == "X-Dev-User-Id")
            assert header["in"] == "header"
    schemas = payload["components"]["schemas"]
    assert "AcceptDiscoveryResponse" in schemas
    assert "SubmissionOriginType" in schemas
    assert set(schemas["SubmissionOriginType"].get("enum", [])) == {"user_input", "discovery"}
    create_props = schemas["CreateUserSubmissionRequest"].get("properties", {})
    assert "origin_type" not in create_props
    assert "origin_discovery_id" not in create_props
