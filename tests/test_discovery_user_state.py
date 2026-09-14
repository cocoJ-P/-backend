from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from app.core.database import SessionLocal
from app.core.time import utc_now
from app.domains.discovery.enums import DiscoveryDisposition, DiscoveryStatus
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
from app.domains.opportunity.seed import seed_demo_opportunities


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


def _create_manual(client, title: str = "发现卡片", priority: str = "normal") -> dict:
    _seed_demo()
    response = client.post(
        "/api/discoveries",
        headers=_header(),
        json={"reference_type": "manual", "title": title, "priority": priority},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _state_count() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(DiscoveryUserState)) or 0)
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


def _get_discovery(discovery_id: str) -> DiscoveryItem:
    db = SessionLocal()
    try:
        row = db.get(DiscoveryItem, UUID(discovery_id))
        assert row is not None
        db.expunge(row)
        return row
    finally:
        db.close()


def _set_created_at(mapping: dict[str, object]) -> None:
    db = SessionLocal()
    try:
        for item_id, created_at in mapping.items():
            row = db.get(DiscoveryItem, UUID(item_id))
            assert row is not None
            row.created_at = created_at
            db.add(row)
        db.commit()
    finally:
        db.close()


def test_mark_seen_first_and_idempotent(client):
    created = _create_manual(client)
    discovery_id = created["id"]
    first = client.post(f"/api/discoveries/{discovery_id}/seen", headers=_header())
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["discovery_id"] == discovery_id
    assert body["user_id"] == str(DEMO_USER_ID)
    assert body["seen_at"]
    assert body["disposition"] is None
    assert _state_count() == 1
    seen_at = body["seen_at"]

    second = client.post(f"/api/discoveries/{discovery_id}/seen", headers=_header())
    assert second.status_code == 200
    assert second.json()["seen_at"] == seen_at
    assert second.json()["disposition"] is None
    assert _state_count() == 1


def test_get_empty_user_state_does_not_create_row(client):
    created = _create_manual(client)
    discovery_id = created["id"]
    response = client.get(f"/api/discoveries/{discovery_id}/user-state", headers=_header())
    assert response.status_code == 200
    body = response.json()
    assert body["seen_at"] is None
    assert body["disposition"] is None
    assert body["disposition_at"] is None
    assert _state_count() == 0


def test_save_implies_seen_and_is_idempotent(client):
    created = _create_manual(client)
    discovery_id = created["id"]
    first = client.patch(
        f"/api/discoveries/{discovery_id}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["disposition"] == "saved"
    assert body["seen_at"]
    assert body["disposition_at"]
    disposition_at = body["disposition_at"]
    assert _get_discovery(discovery_id).status == DiscoveryStatus.ACTIVE.value

    second = client.patch(
        f"/api/discoveries/{discovery_id}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    assert second.status_code == 200
    assert second.json()["disposition_at"] == disposition_at
    assert _state_count() == 1


def test_disposition_transition_and_clear(client):
    created = _create_manual(client)
    discovery_id = created["id"]
    saved = client.patch(
        f"/api/discoveries/{discovery_id}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    seen_at = saved.json()["seen_at"]
    old_at = saved.json()["disposition_at"]

    changed = client.patch(
        f"/api/discoveries/{discovery_id}/user-state",
        headers=_header(),
        json={"disposition": "deprioritized"},
    )
    assert changed.status_code == 200
    assert changed.json()["disposition"] == "deprioritized"
    assert changed.json()["disposition_at"]
    assert changed.json()["seen_at"] == seen_at
    assert _get_state(discovery_id).disposition == DiscoveryDisposition.DEPRIORITIZED.value
    assert _state_count() == 1

    cleared = client.patch(
        f"/api/discoveries/{discovery_id}/user-state",
        headers=_header(),
        json={"disposition": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["disposition"] is None
    assert cleared.json()["disposition_at"] is None
    assert cleared.json()["seen_at"] == seen_at


def test_dismissed_is_rejected(client):
    created = _create_manual(client)
    response = client.patch(
        f"/api/discoveries/{created['id']}/user-state",
        headers=_header(),
        json={"disposition": "dismissed"},
    )
    assert response.status_code == 422


def test_withdraw_preserves_user_state_and_allows_stale_feedback(client):
    created = _create_manual(client)
    discovery_id = created["id"]
    client.patch(
        f"/api/discoveries/{discovery_id}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    withdraw = client.post(f"/api/discoveries/{discovery_id}/withdraw", headers=_header())
    assert withdraw.status_code == 200
    assert withdraw.json()["status"] == "withdrawn"
    assert _get_state(discovery_id) is not None
    assert _get_state(discovery_id).disposition == DiscoveryDisposition.SAVED.value

    seen = client.post(f"/api/discoveries/{discovery_id}/seen", headers=_header())
    assert seen.status_code == 200
    later = client.patch(
        f"/api/discoveries/{discovery_id}/user-state",
        headers=_header(),
        json={"disposition": "deprioritized"},
    )
    assert later.status_code == 200
    assert later.json()["disposition"] == "deprioritized"


def test_enterprise_isolation_for_user_state_apis(client):
    created = _create_manual(client)
    discovery_id = created["id"]
    other = _seed_other_enterprise_user()
    for method, path, json_body in [
        ("post", f"/api/discoveries/{discovery_id}/seen", None),
        ("get", f"/api/discoveries/{discovery_id}/user-state", None),
        ("patch", f"/api/discoveries/{discovery_id}/user-state", {"disposition": "saved"}),
    ]:
        kwargs = {} if json_body is None else {"json": json_body}
        response = getattr(client, method)(path, headers=_header(other), **kwargs)
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "DISCOVERY_NOT_FOUND"


def test_identity_spoof_on_user_state_is_rejected(client):
    created = _create_manual(client)
    response = client.patch(
        f"/api/discoveries/{created['id']}/user-state",
        headers=_header(),
        json={
            "disposition": "saved",
            "user_id": str(uuid4()),
            "enterprise_id": str(uuid4()),
            "seen_at": "2020-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 422


def test_two_users_can_hold_independent_states(client):
    created = _create_manual(client)
    discovery_id = created["id"]
    peer_id = _seed_peer_user()
    a = client.patch(
        f"/api/discoveries/{discovery_id}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    b = client.patch(
        f"/api/discoveries/{discovery_id}/user-state",
        headers=_header(peer_id),
        json={"disposition": "deprioritized"},
    )
    assert a.status_code == 200
    assert b.status_code == 200
    assert _state_count() == 2
    assert _get_state(discovery_id, DEMO_USER_ID).disposition == "saved"
    assert _get_state(discovery_id, peer_id).disposition == "deprioritized"


def test_feed_route_is_not_captured_as_discovery_id(client):
    _seed_demo()
    for path in ("/api/discoveries/feed", "/api/discoveries/saved"):
        response = client.get(path, headers=_header())
        assert response.status_code == 200, path
        assert "items" in response.json()


def test_feed_excludes_saved_and_keeps_deprioritized(client):
    kept = _create_manual(client, title="仍在 Feed")
    saved = _create_manual(client, title="已保存")
    later = _create_manual(client, title="稍后")
    peer_id = _seed_peer_user()
    client.patch(
        f"/api/discoveries/{saved['id']}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    client.patch(
        f"/api/discoveries/{later['id']}/user-state",
        headers=_header(),
        json={"disposition": "deprioritized"},
    )

    own = client.get("/api/discoveries/feed", headers=_header())
    own_ids = [item["id"] for item in own.json()["items"]]
    assert kept["id"] in own_ids
    assert later["id"] in own_ids
    assert saved["id"] not in own_ids

    peer = client.get("/api/discoveries/feed", headers=_header(peer_id))
    peer_ids = [item["id"] for item in peer.json()["items"]]
    assert saved["id"] in peer_ids
    assert later["id"] in peer_ids
    assert kept["id"] in peer_ids

    inventory = client.get("/api/discoveries", headers=_header())
    inventory_ids = [item["id"] for item in inventory.json()["items"]]
    assert saved["id"] in inventory_ids
    assert later["id"] in inventory_ids


def test_feed_ordering_buckets_priority_and_created_at(client):
    unseen_low = _create_manual(client, title="unseen low", priority="low")
    seen_high = _create_manual(client, title="seen high", priority="high")
    deprioritized_high = _create_manual(client, title="deprioritized high", priority="high")
    unseen_high = _create_manual(client, title="unseen high", priority="high")
    unseen_normal = _create_manual(client, title="unseen normal", priority="normal")
    saved = _create_manual(client, title="saved high", priority="high")
    base = utc_now()
    _set_created_at(
        {
            unseen_low["id"]: base,
            seen_high["id"]: base + timedelta(seconds=1),
            deprioritized_high["id"]: base + timedelta(seconds=2),
            unseen_normal["id"]: base + timedelta(seconds=3),
            unseen_high["id"]: base + timedelta(seconds=4),
            saved["id"]: base + timedelta(seconds=5),
        }
    )
    client.post(f"/api/discoveries/{seen_high['id']}/seen", headers=_header())
    client.patch(
        f"/api/discoveries/{deprioritized_high['id']}/user-state",
        headers=_header(),
        json={"disposition": "deprioritized"},
    )
    client.patch(
        f"/api/discoveries/{saved['id']}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )

    feed = client.get("/api/discoveries/feed", headers=_header())
    titles = [item["title"] for item in feed.json()["items"]]
    assert titles == [
        "unseen high",
        "unseen normal",
        "unseen low",
        "seen high",
        "deprioritized high",
    ]
    deprioritized = next(item for item in feed.json()["items"] if item["title"] == "deprioritized high")
    assert deprioritized["current_user_state"]["disposition"] == "deprioritized"


def test_feed_is_pure_read(client):
    created = _create_manual(client)
    response = client.get("/api/discoveries/feed", headers=_header())
    assert response.status_code == 200
    assert created["id"] in [item["id"] for item in response.json()["items"]]
    assert _state_count() == 0
    empty = client.get(f"/api/discoveries/{created['id']}/user-state", headers=_header())
    assert empty.json()["seen_at"] is None


def test_feed_excludes_saved_before_limit(client):
    items = [_create_manual(client, title=f"card {index}") for index in range(5)]
    base = utc_now()
    _set_created_at({item["id"]: base + timedelta(seconds=index) for index, item in enumerate(items)})
    for item in items[2:]:
        client.patch(
            f"/api/discoveries/{item['id']}/user-state",
            headers=_header(),
            json={"disposition": "saved"},
        )
    feed = client.get("/api/discoveries/feed?limit=20", headers=_header())
    ids = [item["id"] for item in feed.json()["items"]]
    assert ids == [items[1]["id"], items[0]["id"]]
    limited = client.get("/api/discoveries/feed?limit=1", headers=_header())
    assert [item["id"] for item in limited.json()["items"]] == [items[1]["id"]]
    paged = client.get("/api/discoveries/feed?limit=1&offset=1", headers=_header())
    assert [item["id"] for item in paged.json()["items"]] == [items[0]["id"]]


def test_saved_collection_scope_order_withdraw_and_pure_read(client):
    older = _create_manual(client, title="较早保存", priority="high")
    newer = _create_manual(client, title="最近保存", priority="low")
    skipped = _create_manual(client, title="仅稍后", priority="high")
    withdrawn = _create_manual(client, title="已撤回保存", priority="high")
    peer_id = _seed_peer_user()
    other = _seed_other_enterprise_user()

    client.patch(
        f"/api/discoveries/{older['id']}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    client.patch(
        f"/api/discoveries/{newer['id']}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    client.patch(
        f"/api/discoveries/{skipped['id']}/user-state",
        headers=_header(),
        json={"disposition": "deprioritized"},
    )
    client.patch(
        f"/api/discoveries/{withdrawn['id']}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    db = SessionLocal()
    try:
        base = utc_now()
        for item_id, at in (
            (older["id"], base),
            (newer["id"], base + timedelta(seconds=5)),
            (withdrawn["id"], base + timedelta(seconds=8)),
        ):
            row = db.scalars(
                select(DiscoveryUserState).where(DiscoveryUserState.discovery_id == UUID(item_id))
            ).first()
            assert row is not None
            row.disposition_at = at
            db.add(row)
        db.commit()
    finally:
        db.close()

    withdraw = client.post(f"/api/discoveries/{withdrawn['id']}/withdraw", headers=_header())
    assert withdraw.status_code == 200

    before = _state_count()
    saved = client.get("/api/discoveries/saved", headers=_header())
    assert saved.status_code == 200
    titles = [item["title"] for item in saved.json()["items"]]
    assert titles == ["最近保存", "较早保存"]
    assert all(item["current_user_state"]["disposition"] == "saved" for item in saved.json()["items"])
    assert skipped["id"] not in [item["id"] for item in saved.json()["items"]]
    assert withdrawn["id"] not in [item["id"] for item in saved.json()["items"]]
    assert _state_count() == before
    assert _get_state(withdrawn["id"]).disposition == DiscoveryDisposition.SAVED.value

    peer = client.get("/api/discoveries/saved", headers=_header(peer_id))
    assert peer.json()["items"] == []
    isolated = client.get("/api/discoveries/saved", headers=_header(other))
    assert isolated.status_code == 200
    assert isolated.json()["items"] == []


def test_legacy_dismissed_rows_migrate_to_deprioritized(client):
    created = _create_manual(client, title="历史 dismissed")
    patched = client.patch(
        f"/api/discoveries/{created['id']}/user-state",
        headers=_header(),
        json={"disposition": "deprioritized"},
    )
    assert patched.status_code == 200
    db = SessionLocal()
    try:
        row = db.scalars(
            select(DiscoveryUserState).where(
                DiscoveryUserState.discovery_id == UUID(created["id"])
            )
        ).first()
        assert row is not None
        seen_at = row.seen_at
        disposition_at = row.disposition_at
        created_at = row.created_at
        updated_at = row.updated_at
        db.execute(
            text(
                "UPDATE discovery_user_states SET disposition = 'dismissed' "
                "WHERE discovery_id = :discovery_id"
            ),
            {"discovery_id": created["id"]},
        )
        db.commit()
        db.execute(
            text(
                "UPDATE discovery_user_states "
                "SET disposition = 'deprioritized' "
                "WHERE disposition = 'dismissed'"
            )
        )
        db.commit()
        migrated = db.scalars(
            select(DiscoveryUserState).where(
                DiscoveryUserState.discovery_id == UUID(created["id"])
            )
        ).first()
        assert migrated is not None
        assert migrated.disposition == "deprioritized"
        assert migrated.seen_at == seen_at
        assert migrated.disposition_at == disposition_at
        assert migrated.created_at == created_at
        assert migrated.updated_at == updated_at
        assert db.get(DiscoveryUserState, migrated.id) is not None
    finally:
        db.close()


def test_enterprise_feedback_list_scope_filter_and_payload(client):
    created = _create_manual(client, title="反馈列表标题")
    peer_id = _seed_peer_user()
    other = _seed_other_enterprise_user()
    client.patch(
        f"/api/discoveries/{created['id']}/user-state",
        headers=_header(),
        json={"disposition": "saved"},
    )
    client.patch(
        f"/api/discoveries/{created['id']}/user-state",
        headers=_header(peer_id),
        json={"disposition": "deprioritized"},
    )

    own = client.get("/api/discovery-user-states", headers=_header())
    assert own.status_code == 200
    assert len(own.json()["items"]) == 2
    payload = own.json()["items"][0]
    assert "summary" not in payload["discovery"]
    assert "reason" not in payload["discovery"]
    assert payload["discovery"]["title"] == "反馈列表标题"
    assert payload["user"]["display_name"]
    assert "linked_submission" in payload
    assert payload["linked_submission"] is None

    saved_only = client.get("/api/discovery-user-states?disposition=saved", headers=_header())
    assert [item["disposition"] for item in saved_only.json()["items"]] == ["saved"]

    by_user = client.get(f"/api/discovery-user-states?user_id={peer_id}", headers=_header())
    assert len(by_user.json()["items"]) == 1
    assert by_user.json()["items"][0]["user"]["id"] == str(peer_id)

    by_discovery = client.get(
        f"/api/discovery-user-states?discovery_id={created['id']}",
        headers=_header(),
    )
    assert len(by_discovery.json()["items"]) == 2

    isolated = client.get("/api/discovery-user-states", headers=_header(other))
    assert isolated.status_code == 200
    assert isolated.json()["items"] == []


def test_user_state_apis_require_identity(client):
    created = _create_manual(client)
    discovery_id = created["id"]
    endpoints = [
        ("get", "/api/discoveries/feed", None),
        ("get", "/api/discoveries/saved", None),
        ("post", f"/api/discoveries/{discovery_id}/accept", None),
        ("post", f"/api/discoveries/{discovery_id}/seen", None),
        ("get", f"/api/discoveries/{discovery_id}/user-state", None),
        ("patch", f"/api/discoveries/{discovery_id}/user-state", {"disposition": "saved"}),
        ("get", "/api/discovery-user-states", None),
    ]
    for method, path, json_body in endpoints:
        kwargs = {} if json_body is None else {"json": json_body}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "DEV_IDENTITY_REQUIRED"


def test_openapi_user_state_routes_require_dev_identity(client):
    payload = client.get("/openapi.json").json()
    paths = payload["paths"]
    expected = {
        "/api/discoveries/feed": ["get"],
        "/api/discoveries/saved": ["get"],
        "/api/discoveries/{discovery_id}/accept": ["post"],
        "/api/discoveries/{discovery_id}/seen": ["post"],
        "/api/discoveries/{discovery_id}/user-state": ["get", "patch"],
        "/api/discovery-user-states": ["get"],
    }
    for path, methods in expected.items():
        assert path in paths, path
        for method in methods:
            parameters = paths[path][method].get("parameters", [])
            header = next(item for item in parameters if item.get("name") == "X-Dev-User-Id")
            assert header["in"] == "header"
    schemas = payload["components"]["schemas"]
    assert "UpdateDiscoveryUserStateRequest" in schemas
    assert "DiscoveryUserStateResponse" in schemas
    assert "DiscoveryFeedResponse" in schemas
    assert schemas["UpdateDiscoveryUserStateRequest"].get("additionalProperties") is False
    disposition_schema = schemas["DiscoveryDisposition"]
    values = set(disposition_schema.get("enum", []))
    assert values == {"saved", "deprioritized"}
    assert "DiscoveryUserStateListItem" in schemas
    assert "linked_submission" in schemas["DiscoveryUserStateListItem"]["properties"]
    assert "LinkedDiscoverySubmission" in schemas
    assert "dismissed" not in values


def test_existing_contracts_remain_compatible(client):
    _seed_demo()
    me = client.get("/api/me", headers=_header())
    assert me.status_code == 200
    ingest = client.post(
        "/api/content/ingest",
        json={"content_type": "text", "content": "回归测试正文需要足够长度。"},
    )
    assert ingest.status_code == 201
    submission = client.post(
        "/api/user-submissions",
        headers=_header(),
        json={"input_type": "text", "content": "回归提交正文需要足够长度。"},
    )
    assert submission.status_code == 201
    created = client.post(
        "/api/discoveries",
        headers=_header(),
        json={"reference_type": "manual", "title": "库存仍可见"},
    )
    assert created.status_code == 201
    client.patch(
        f"/api/discoveries/{created.json()['id']}/user-state",
        headers=_header(),
        json={"disposition": "deprioritized"},
    )
    inventory = client.get("/api/discoveries", headers=_header())
    assert created.json()["id"] in [item["id"] for item in inventory.json()["items"]]
    feed = client.get("/api/discoveries/feed", headers=_header())
    assert feed.status_code == 200
    seen = client.post(f"/api/discoveries/{created.json()['id']}/seen", headers=_header())
    assert seen.status_code == 200
    state = client.get(f"/api/discoveries/{created.json()['id']}/user-state", headers=_header())
    assert state.status_code == 200
    listing = client.get("/api/discovery-user-states", headers=_header())
    assert listing.status_code == 200
    assert listing.json()["items"][0]["linked_submission"] is None
