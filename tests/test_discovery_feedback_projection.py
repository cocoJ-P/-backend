from uuid import UUID

from sqlalchemy import event, func, select

from app.core.database import SessionLocal, engine
from app.core.exceptions import AppException
from app.domains.discovery.user_state_models import DiscoveryUserState
from app.domains.identity.seed import DEMO_USER_ID
from app.domains.submission.models import UserSubmission
from app.integrations.llm.providers.fake import FakeLLMProvider
from tests.test_discovery_user_state import (
    _create_manual,
    _header,
    _seed_other_enterprise_user,
    _seed_peer_user,
)
from tests.test_submissions import _success_payload, _use_fake_llm


def _feedback(client, headers=None, **params):
    response = client.get(
        "/api/discovery-user-states",
        headers=_header() if headers is None else headers,
        params=params,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _item_for(client, discovery_id: str, user_id=DEMO_USER_ID) -> dict:
    payload = _feedback(client, discovery_id=discovery_id)
    matched = [
        item
        for item in payload["items"]
        if item["discovery"]["id"] == discovery_id and item["user"]["id"] == str(user_id)
    ]
    assert len(matched) == 1, payload
    return matched[0]


def _count_submissions() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(UserSubmission)) or 0)
    finally:
        db.close()


def _get_state(discovery_id: str, user_id=DEMO_USER_ID) -> DiscoveryUserState:
    db = SessionLocal()
    try:
        row = db.scalars(
            select(DiscoveryUserState).where(
                DiscoveryUserState.discovery_id == UUID(discovery_id),
                DiscoveryUserState.user_id == user_id,
            )
        ).first()
        assert row is not None
        db.expunge(row)
        return row
    finally:
        db.close()


def test_feedback_seen_only_has_null_linked_submission(client):
    item = _create_manual(client, title="只看过")
    seen = client.post(f"/api/discoveries/{item['id']}/seen", headers=_header())
    assert seen.status_code == 200
    assert seen.json()["disposition"] is None

    feedback = _item_for(client, item["id"])
    assert feedback["seen_at"] is not None
    assert feedback["disposition"] is None
    assert feedback["linked_submission"] is None


def test_feedback_deprioritized_has_null_linked_submission(client):
    item = _create_manual(client, title="稍后")
    patched = client.patch(
        f"/api/discoveries/{item['id']}/user-state",
        headers=_header(),
        json={"disposition": "deprioritized"},
    )
    assert patched.status_code == 200

    feedback = _item_for(client, item["id"])
    assert feedback["disposition"] == "deprioritized"
    assert feedback["linked_submission"] is None


def test_feedback_accepted_pending_links_submission(client):
    item = _create_manual(client, title="待处理发现")
    accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert accepted.status_code == 201, accepted.text
    submission_id = accepted.json()["submission"]["id"]

    feedback = _item_for(client, item["id"])
    assert feedback["disposition"] == "saved"
    linked = feedback["linked_submission"]
    assert linked is not None
    assert linked["id"] == submission_id
    assert linked["status"] == "pending"
    assert linked["origin_type"] == "discovery"
    assert linked["created_at"]
    assert linked["completed_at"] is None
    assert linked["failure_stage"] is None
    assert linked["error_code"] is None
    assert linked["error_message"] is None
    assert "display_title" not in linked
    assert "input_preview" not in linked
    assert "input_content" not in linked


def test_feedback_accepted_succeeded_keeps_user_state_order(client, monkeypatch):
    item = _create_manual(client, title="2026年度科技创新项目")
    accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert accepted.status_code == 201, accepted.text
    submission_id = accepted.json()["submission"]["id"]
    before = _get_state(item["id"]).updated_at

    _use_fake_llm(monkeypatch, FakeLLMProvider(_success_payload("2026年度科技创新项目")))
    processed = client.post(
        f"/api/user-submissions/{submission_id}/process",
        headers=_header(),
    )
    assert processed.status_code == 200, processed.text
    assert processed.json()["submission"]["status"] == "succeeded"
    assert _get_state(item["id"]).updated_at == before

    feedback = _item_for(client, item["id"])
    linked = feedback["linked_submission"]
    assert feedback["disposition"] == "saved"
    assert linked["id"] == submission_id
    assert linked["status"] == "succeeded"
    assert linked["completed_at"] is not None
    assert linked["failure_stage"] is None
    assert linked["error_code"] is None


def test_feedback_accepted_failed_keeps_safe_failure_info(client, monkeypatch):
    item = _create_manual(client, title="解析失败发现")
    accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert accepted.status_code == 201, accepted.text
    submission_id = accepted.json()["submission"]["id"]

    def fail_ingest(*_args, **_kwargs):
        raise AppException("FETCH_FAILED", "Could not fetch URL", status_code=502)

    monkeypatch.setattr("app.domains.submission.orchestration.ingest", fail_ingest)
    processed = client.post(
        f"/api/user-submissions/{submission_id}/process",
        headers=_header(),
    )
    assert processed.status_code == 502

    feedback = _item_for(client, item["id"])
    linked = feedback["linked_submission"]
    assert linked["id"] == submission_id
    assert linked["status"] == "failed"
    assert linked["failure_stage"] == "ingest"
    assert linked["error_code"] == "FETCH_FAILED"
    assert linked["error_message"]
    assert "Traceback" not in linked["error_message"]
    assert "Authorization" not in linked["error_message"]


def test_feedback_legacy_saved_does_not_create_submission(client):
    item = _create_manual(client, title="仅保存")
    patched = client.patch(
        f"/api/discoveries/{item['id']}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    assert patched.status_code == 200
    assert _count_submissions() == 0

    feedback = _item_for(client, item["id"])
    assert feedback["disposition"] == "saved"
    assert feedback["linked_submission"] is None
    assert _count_submissions() == 0


def test_feedback_two_users_do_not_cross_link_submissions(client):
    item = _create_manual(client, title="双用户发现")
    peer_id = _seed_peer_user()
    accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert accepted.status_code == 201, accepted.text
    deprioritized = client.patch(
        f"/api/discoveries/{item['id']}/user-state",
        headers=_header(peer_id),
        json={"disposition": "deprioritized"},
    )
    assert deprioritized.status_code == 200

    items = _feedback(client, discovery_id=item["id"])["items"]
    assert len(items) == 2
    by_user = {row["user"]["id"]: row for row in items}
    own = by_user[str(DEMO_USER_ID)]
    peer = by_user[str(peer_id)]
    assert own["disposition"] == "saved"
    assert own["linked_submission"] is not None
    assert own["linked_submission"]["id"] == accepted.json()["submission"]["id"]
    assert peer["disposition"] == "deprioritized"
    assert peer["linked_submission"] is None


def test_feedback_hides_other_enterprise_user_state_and_submission(client):
    item = _create_manual(client, title="企业隔离发现")
    accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert accepted.status_code == 201, accepted.text
    other = _seed_other_enterprise_user()
    isolated = _feedback(client, headers=_header(other))
    assert isolated["items"] == []


def test_feedback_keeps_withdrawn_discovery_history(client):
    item = _create_manual(client, title="撤回后仍可见")
    accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
    assert accepted.status_code == 201, accepted.text
    withdraw = client.post(f"/api/discoveries/{item['id']}/withdraw", headers=_header())
    assert withdraw.status_code == 200
    assert withdraw.json()["status"] == "withdrawn"

    feedback = _item_for(client, item["id"])
    assert feedback["discovery"]["status"] == "withdrawn"
    assert feedback["disposition"] == "saved"
    assert feedback["linked_submission"] is not None
    assert feedback["linked_submission"]["id"] == accepted.json()["submission"]["id"]
    assert feedback["linked_submission"]["status"] == "pending"


def test_feedback_does_not_link_user_input_submission(client):
    item = _create_manual(client, title="普通输入不应关联")
    client.post(f"/api/discoveries/{item['id']}/seen", headers=_header())
    created = client.post(
        "/api/user-submissions",
        headers=_header(),
        json={"input_type": "text", "content": "用户自己粘贴的申报通知正文。"},
    )
    assert created.status_code == 201, created.text

    feedback = _item_for(client, item["id"])
    assert feedback["linked_submission"] is None


def test_feedback_list_is_pure_read(client):
    item = _create_manual(client, title="纯读取")
    client.post(f"/api/discoveries/{item['id']}/seen", headers=_header())
    before_state = _get_state(item["id"]).updated_at
    before_count = _count_submissions()
    _item_for(client, item["id"])
    assert _get_state(item["id"]).updated_at == before_state
    assert _count_submissions() == before_count


def test_feedback_list_loads_linked_submissions_without_n_plus_one(client):
    created = [
        _create_manual(client, title="批量反馈一"),
        _create_manual(client, title="批量反馈二"),
        _create_manual(client, title="批量反馈三"),
    ]
    for item in created:
        accepted = client.post(f"/api/discoveries/{item['id']}/accept", headers=_header())
        assert accepted.status_code == 201, accepted.text

    statements: list[str] = []

    def before_cursor_execute(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        payload = _feedback(client)
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert len(payload["items"]) == 3
    normalized = [" ".join(item.lower().split()) for item in statements]
    independent = [item for item in normalized if "from user_submissions" in item]
    joined = [item for item in normalized if "join user_submissions" in item]
    assert independent == []
    assert len(joined) == 1
