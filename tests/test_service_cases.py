from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.core.time import utc_now
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
from app.domains.opportunity.seed import seed_demo_opportunities
from app.domains.service_case.enums import ServiceCaseStatus
from app.domains.service_case.models import ServiceCase
from app.domains.service_case.repository import get_service_case_by_submission_id
from app.domains.service_case.service import transition_service_case_status
from app.domains.submission.enums import SubmissionStatus
from app.domains.submission.models import UserSubmission
from app.integrations.llm.providers.fake import FakeLLMProvider
from tests.test_submissions import NOTICE, _success_payload, _use_fake_llm


def _header(user_id=DEMO_USER_ID) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user_id)}


def _seed_identity() -> None:
    db = SessionLocal()
    try:
        seed_demo_identity(db)
    finally:
        db.close()


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


def _create_submission(client, content: str = NOTICE, user_id=DEMO_USER_ID) -> dict:
    _seed_identity()
    response = client.post(
        "/api/user-submissions",
        headers=_header(user_id),
        json={"input_type": "text", "content": content},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _succeed_submission(client, monkeypatch, submission_id: str, user_id=DEMO_USER_ID) -> dict:
    _use_fake_llm(monkeypatch, FakeLLMProvider(_success_payload(NOTICE)))
    response = client.post(
        f"/api/user-submissions/{submission_id}/process",
        headers=_header(user_id),
    )
    assert response.status_code == 200, response.text
    assert response.json()["submission"]["status"] == "succeeded"
    return response.json()


def _create_succeeded_submission(client, monkeypatch, user_id=DEMO_USER_ID) -> str:
    created = _create_submission(client, user_id=user_id)
    _succeed_submission(client, monkeypatch, created["id"], user_id=user_id)
    return created["id"]


def _set_submission_status(submission_id: str, status: str) -> None:
    db = SessionLocal()
    try:
        row = db.get(UserSubmission, UUID(submission_id))
        assert row is not None
        row.status = status
        db.commit()
    finally:
        db.close()


def _count_cases() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(ServiceCase)) or 0)
    finally:
        db.close()


def _get_case(service_case_id: str) -> ServiceCase:
    db = SessionLocal()
    try:
        row = db.get(ServiceCase, UUID(service_case_id))
        assert row is not None
        db.expunge(row)
        return row
    finally:
        db.close()


def test_create_service_case_from_user_input(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    response = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    case = body["service_case"]
    assert case["status"] == "open"
    assert case["submission_id"] == submission_id
    assert case["created_by_user_id"] == str(DEMO_USER_ID)
    assert case["enterprise_id"] == str(DEMO_ENTERPRISE_ID)
    assert case["title"]
    assert case["completed_at"] is None
    assert case["closed_at"] is None
    assert _count_cases() == 1


def test_create_service_case_from_discovery_origin(client, monkeypatch):
    _seed_demo()
    created = client.post(
        "/api/discoveries",
        headers=_header(),
        json={"reference_type": "manual", "title": "发现办理事项", "summary": NOTICE.strip()},
    )
    assert created.status_code == 201, created.text
    accepted = client.post(f"/api/discoveries/{created.json()['id']}/accept", headers=_header())
    assert accepted.status_code == 201, accepted.text
    submission_id = accepted.json()["submission"]["id"]
    _succeed_submission(client, monkeypatch, submission_id)
    response = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert response.status_code == 201, response.text
    case = response.json()["service_case"]
    assert case["status"] == "open"
    assert case["submission_id"] == submission_id
    stored = _get_case(case["id"])
    assert stored.created_by_user_id == DEMO_USER_ID


def test_pending_submission_cannot_create_service_case(client):
    created = _create_submission(client)
    response = client.post(
        f"/api/user-submissions/{created['id']}/service-case",
        headers=_header(),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUBMISSION_NOT_READY_FOR_SERVICE"
    assert _count_cases() == 0


def test_ingesting_submission_cannot_create_service_case(client):
    created = _create_submission(client)
    _set_submission_status(created["id"], SubmissionStatus.INGESTING.value)
    response = client.post(
        f"/api/user-submissions/{created['id']}/service-case",
        headers=_header(),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUBMISSION_NOT_READY_FOR_SERVICE"
    assert _count_cases() == 0


def test_analyzing_submission_cannot_create_service_case(client):
    created = _create_submission(client)
    _set_submission_status(created["id"], SubmissionStatus.ANALYZING.value)
    response = client.post(
        f"/api/user-submissions/{created['id']}/service-case",
        headers=_header(),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUBMISSION_NOT_READY_FOR_SERVICE"
    assert _count_cases() == 0


def test_failed_submission_cannot_create_service_case(client, monkeypatch):
    created = _create_submission(client)

    def fail_ingest(*_args, **_kwargs):
        raise AppException("FETCH_FAILED", "Could not fetch URL", status_code=502)

    monkeypatch.setattr("app.domains.submission.orchestration.ingest", fail_ingest)
    processed = client.post(
        f"/api/user-submissions/{created['id']}/process",
        headers=_header(),
    )
    assert processed.status_code == 502
    response = client.post(
        f"/api/user-submissions/{created['id']}/service-case",
        headers=_header(),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUBMISSION_NOT_READY_FOR_SERVICE"
    assert _count_cases() == 0


def test_create_service_case_is_idempotent(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    first = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert first.status_code == 201
    case_id = first.json()["service_case"]["id"]
    second = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["service_case"]["id"] == case_id
    assert _count_cases() == 1


def test_create_recovers_from_unique_integrity_error(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    first = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert first.status_code == 201
    case_id = first.json()["service_case"]["id"]
    calls = {"n": 0}
    real = get_service_case_by_submission_id

    def flaky_lookup(db, current_submission_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real(db, current_submission_id)

    monkeypatch.setattr(
        "app.domains.service_case.service.get_service_case_by_submission_id",
        flaky_lookup,
    )
    second = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert second.status_code == 200, second.text
    assert second.json()["created"] is False
    assert second.json()["service_case"]["id"] == case_id
    assert _count_cases() == 1
    assert calls["n"] >= 2


def test_other_user_cannot_create_service_case_for_peer_submission(client, monkeypatch):
    peer_id = _seed_peer_user()
    submission_id = _create_succeeded_submission(client, monkeypatch)
    response = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(peer_id),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SUBMISSION_NOT_FOUND"
    assert _count_cases() == 0


def test_service_case_detail_and_list_are_enterprise_isolated(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    created = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    case_id = created.json()["service_case"]["id"]
    other = _seed_other_enterprise_user()
    hidden = client.get(f"/api/service-cases/{case_id}", headers=_header(other))
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "SERVICE_CASE_NOT_FOUND"
    listing = client.get("/api/service-cases", headers=_header(other))
    assert listing.status_code == 200
    assert listing.json()["items"] == []


def test_enterprise_list_filters_and_created_at_desc(client, monkeypatch):
    peer_id = _seed_peer_user()
    first_id = _create_succeeded_submission(client, monkeypatch)
    second_id = _create_succeeded_submission(client, monkeypatch, user_id=peer_id)
    first = client.post(f"/api/user-submissions/{first_id}/service-case", headers=_header())
    second = client.post(
        f"/api/user-submissions/{second_id}/service-case",
        headers=_header(peer_id),
    )
    assert first.status_code == 201
    assert second.status_code == 201
    db = SessionLocal()
    try:
        base = utc_now()
        older = db.get(ServiceCase, UUID(first.json()["service_case"]["id"]))
        newer = db.get(ServiceCase, UUID(second.json()["service_case"]["id"]))
        assert older is not None
        assert newer is not None
        older.created_at = base
        newer.created_at = base + timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    listing = client.get("/api/service-cases", headers=_header())
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert [item["id"] for item in items] == [
        second.json()["service_case"]["id"],
        first.json()["service_case"]["id"],
    ]
    assert "input_content" not in items[0]["submission"]
    assert "intelligence" not in items[0]
    open_only = client.get("/api/service-cases?status=open", headers=_header())
    assert [item["status"] for item in open_only.json()["items"]] == ["open", "open"]
    by_user = client.get(f"/api/service-cases?user_id={peer_id}", headers=_header())
    assert [item["id"] for item in by_user.json()["items"]] == [second.json()["service_case"]["id"]]
    completed = client.get("/api/service-cases?status=completed", headers=_header())
    assert completed.json()["items"] == []


def test_mine_is_current_user_scoped(client, monkeypatch):
    peer_id = _seed_peer_user()
    own_id = _create_succeeded_submission(client, monkeypatch)
    peer_submission = _create_succeeded_submission(client, monkeypatch, user_id=peer_id)
    own = client.post(f"/api/user-submissions/{own_id}/service-case", headers=_header())
    peer = client.post(
        f"/api/user-submissions/{peer_submission}/service-case",
        headers=_header(peer_id),
    )
    mine = client.get("/api/service-cases/mine", headers=_header())
    assert [item["id"] for item in mine.json()["items"]] == [own.json()["service_case"]["id"]]
    peer_mine = client.get("/api/service-cases/mine", headers=_header(peer_id))
    assert [item["id"] for item in peer_mine.json()["items"]] == [peer.json()["service_case"]["id"]]


def test_submission_mine_and_detail_projection(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    mine = client.get("/api/user-submissions/mine", headers=_header())
    matched = next(item for item in mine.json()["items"] if item["id"] == submission_id)
    assert matched["linked_service_case"] is None
    detail = client.get(f"/api/user-submissions/{submission_id}", headers=_header())
    assert detail.json()["linked_service_case"] is None
    before = _count_cases()

    created = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert created.status_code == 201
    mine_after = client.get("/api/user-submissions/mine", headers=_header())
    linked = next(item for item in mine_after.json()["items"] if item["id"] == submission_id)[
        "linked_service_case"
    ]
    assert linked["id"] == created.json()["service_case"]["id"]
    assert linked["status"] == "open"
    assert "feishu" not in linked
    detail_after = client.get(f"/api/user-submissions/{submission_id}", headers=_header())
    assert detail_after.json()["linked_service_case"]["id"] == created.json()["service_case"]["id"]
    assert _count_cases() == before + 1


def test_submission_projection_is_pure_read(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    client.get("/api/user-submissions/mine", headers=_header())
    client.get(f"/api/user-submissions/{submission_id}", headers=_header())
    assert _count_cases() == 0


def test_withdrawn_discovery_does_not_block_service_case(client, monkeypatch):
    _seed_demo()
    created = client.post(
        "/api/discoveries",
        headers=_header(),
        json={"reference_type": "manual", "title": "撤回后仍可办理", "summary": NOTICE.strip()},
    )
    discovery_id = created.json()["id"]
    accepted = client.post(f"/api/discoveries/{discovery_id}/accept", headers=_header())
    submission_id = accepted.json()["submission"]["id"]
    _succeed_submission(client, monkeypatch, submission_id)
    withdraw = client.post(f"/api/discoveries/{discovery_id}/withdraw", headers=_header())
    assert withdraw.status_code == 200
    response = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    assert response.status_code == 201, response.text
    assert response.json()["service_case"]["status"] == "open"


def test_service_case_detail_returns_lightweight_submission(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    created = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    detail = client.get(
        f"/api/service-cases/{created.json()['service_case']['id']}",
        headers=_header(),
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["title"]
    assert body["created_by_user"]["id"] == str(DEMO_USER_ID)
    assert body["submission"]["id"] == submission_id
    assert body["submission"]["status"] == "succeeded"
    assert body["submission"]["input_preview"]
    assert "input_content" not in body["submission"]
    assert "intelligence" not in body


def test_status_transitions_and_timestamps(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    created = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    case_id = UUID(created.json()["service_case"]["id"])
    db = SessionLocal()
    try:
        case = db.get(ServiceCase, case_id)
        assert case is not None
        transition_service_case_status(db, case, ServiceCaseStatus.IN_PROGRESS)
        progressed = db.get(ServiceCase, case_id)
        assert progressed.status == "in_progress"
        assert progressed.completed_at is None
        assert progressed.closed_at is None
        transition_service_case_status(db, progressed, ServiceCaseStatus.COMPLETED)
        completed = db.get(ServiceCase, case_id)
        assert completed.status == "completed"
        assert completed.completed_at is not None
        assert completed.closed_at is None
    finally:
        db.close()

    closed_submission = _create_succeeded_submission(client, monkeypatch)
    closed_created = client.post(
        f"/api/user-submissions/{closed_submission}/service-case",
        headers=_header(),
    )
    db = SessionLocal()
    try:
        case = db.get(ServiceCase, UUID(closed_created.json()["service_case"]["id"]))
        assert case is not None
        transition_service_case_status(db, case, ServiceCaseStatus.CLOSED)
        closed = db.get(ServiceCase, case.id)
        assert closed.status == "closed"
        assert closed.closed_at is not None
        assert closed.completed_at is None
        in_progress_id = _create_succeeded_submission(client, monkeypatch)
        in_progress_created = client.post(
            f"/api/user-submissions/{in_progress_id}/service-case",
            headers=_header(),
        )
        moving = db.get(ServiceCase, UUID(in_progress_created.json()["service_case"]["id"]))
        transition_service_case_status(db, moving, ServiceCaseStatus.IN_PROGRESS)
        transition_service_case_status(db, moving, ServiceCaseStatus.CLOSED)
        closed_from_progress = db.get(ServiceCase, moving.id)
        assert closed_from_progress.status == "closed"
        assert closed_from_progress.closed_at is not None
        assert closed_from_progress.completed_at is None
    finally:
        db.close()


def test_invalid_status_transitions_are_rejected(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    created = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    db = SessionLocal()
    try:
        case = db.get(ServiceCase, UUID(created.json()["service_case"]["id"]))
        assert case is not None
        try:
            transition_service_case_status(db, case, ServiceCaseStatus.COMPLETED)
            raise AssertionError("open → completed should fail")
        except AppException as exc:
            assert exc.code == "INVALID_SERVICE_CASE_TRANSITION"
            assert exc.status_code == 409
        transition_service_case_status(db, case, ServiceCaseStatus.IN_PROGRESS)
        transition_service_case_status(db, case, ServiceCaseStatus.COMPLETED)
        for target in (ServiceCaseStatus.IN_PROGRESS, ServiceCaseStatus.CLOSED, ServiceCaseStatus.OPEN):
            try:
                transition_service_case_status(db, case, target)
                raise AssertionError(f"completed → {target.value} should fail")
            except AppException as exc:
                assert exc.code == "INVALID_SERVICE_CASE_TRANSITION"
        closed_id = _create_succeeded_submission(client, monkeypatch)
        closed_created = client.post(
            f"/api/user-submissions/{closed_id}/service-case",
            headers=_header(),
        )
        closed = db.get(ServiceCase, UUID(closed_created.json()["service_case"]["id"]))
        transition_service_case_status(db, closed, ServiceCaseStatus.CLOSED)
        for target in (ServiceCaseStatus.OPEN, ServiceCaseStatus.IN_PROGRESS, ServiceCaseStatus.COMPLETED):
            try:
                transition_service_case_status(db, closed, target)
                raise AssertionError(f"closed → {target.value} should fail")
            except AppException as exc:
                assert exc.code == "INVALID_SERVICE_CASE_TRANSITION"
    finally:
        db.close()


def test_service_case_apis_require_identity(client, monkeypatch):
    submission_id = _create_succeeded_submission(client, monkeypatch)
    created = client.post(
        f"/api/user-submissions/{submission_id}/service-case",
        headers=_header(),
    )
    case_id = created.json()["service_case"]["id"]
    endpoints = [
        ("post", f"/api/user-submissions/{submission_id}/service-case", None),
        ("get", "/api/service-cases", None),
        ("get", "/api/service-cases/mine", None),
        ("get", f"/api/service-cases/{case_id}", None),
    ]
    for method, path, json_body in endpoints:
        kwargs = {} if json_body is None else {"json": json_body}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "DEV_IDENTITY_REQUIRED"


def test_openapi_service_case_routes_and_no_status_mutation(client):
    payload = client.get("/openapi.json").json()
    paths = payload["paths"]
    expected = {
        "/api/user-submissions/{submission_id}/service-case": ["post"],
        "/api/service-cases": ["get"],
        "/api/service-cases/mine": ["get"],
        "/api/service-cases/{service_case_id}": ["get"],
    }
    for path, methods in expected.items():
        assert path in paths, path
        for method in methods:
            parameters = paths[path][method].get("parameters", [])
            header = next(item for item in parameters if item.get("name") == "X-Dev-User-Id")
            assert header["in"] == "header"
    assert "/api/service-cases/{service_case_id}/status" not in paths
    patch_methods = paths.get("/api/service-cases/{service_case_id}", {})
    assert "patch" not in patch_methods
    schemas = payload["components"]["schemas"]
    assert "CreateServiceCaseResponse" in schemas
    assert "LinkedServiceCase" in schemas
    assert "linked_service_case" in schemas["UserSubmissionSummary"]["properties"]
    assert "linked_service_case" in schemas["UserSubmissionDetail"]["properties"]
    assert set(schemas["ServiceCaseStatus"].get("enum", [])) == {
        "open",
        "in_progress",
        "completed",
        "closed",
    }
