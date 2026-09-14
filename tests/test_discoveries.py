from datetime import date, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.database import Base, SessionLocal
from app.core.time import utc_now
from app.domains.discovery.enums import DiscoveryPriority, DiscoveryStatus
from app.domains.discovery.models import DiscoveryItem
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
from app.domains.opportunity.enums import SourceType
from app.domains.opportunity.models import Opportunity, OpportunitySource
from app.domains.opportunity.repository import add_source
from app.domains.opportunity.seed import (
    DEMO_POLICY_ID,
    DEMO_POLICY_SOURCE_OFFICIAL_ID,
    seed_demo_opportunities,
)
from app.integrations.content.models import IngestedContent
from app.integrations.content.repository import add_ingested_content


def _header(user_id=DEMO_USER_ID) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user_id)}


def _seed_demo() -> None:
    db = SessionLocal()
    try:
        seed_demo_identity(db)
        seed_demo_opportunities(db)
    finally:
        db.close()


def _seed_other_identity() -> UUID:
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


def _create_manual(client, **overrides):
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
    return response


def _get_item(discovery_id: str) -> DiscoveryItem:
    db = SessionLocal()
    try:
        row = db.get(DiscoveryItem, UUID(discovery_id))
        assert row is not None
        db.expunge(row)
        return row
    finally:
        db.close()


def test_create_manual_discovery_uses_current_identity(client):
    response = _create_manual(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "active"
    assert body["priority"] == "normal"
    assert body["reference_type"] == "manual"
    assert body["title"] == "人工智能企业产业对接活动"
    assert body["summary"] == "面向成长阶段科技企业开放"
    assert body["reason"] == "与你当前业务方向相关"
    assert body["opportunity_id"] is None
    assert body["source_id"] is None
    assert body["opportunity_type"] is None
    assert body["created_by"]["id"] == str(DEMO_USER_ID)
    assert body["created_by"]["display_name"] == "Demo User"

    stored = _get_item(body["id"])
    assert stored.enterprise_id == DEMO_ENTERPRISE_ID
    assert stored.created_by_user_id == DEMO_USER_ID
    assert stored.status == DiscoveryStatus.ACTIVE.value


def test_create_rejects_spoofed_identity_fields(client):
    _seed_demo()
    response = client.post(
        "/api/discoveries",
        headers=_header(),
        json={
            "reference_type": "manual",
            "title": "人工智能企业产业对接活动",
            "enterprise_id": str(uuid4()),
            "created_by_user_id": str(uuid4()),
        },
    )
    assert response.status_code == 422


def test_create_opportunity_snapshots_fields(client):
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
    body = response.json()
    assert body["reference_type"] == "opportunity"
    assert body["opportunity_id"] == str(DEMO_POLICY_ID)
    assert body["source_id"] is None
    assert body["title"] == "北京市科技型企业研发创新支持专项"
    assert body["summary"] == "支持科技型企业持续加大研发投入，对符合条件的研发项目给予资金支持。"
    assert body["opportunity_type"] == "policy"
    assert body["issuer"] == "北京市科学技术委员会"
    assert body["region"] == "北京市"
    assert body["deadline"] == "2026-10-15"
    assert body["reference_url"] == "https://example.beijing.gov.cn/rd-innovation-support"
    assert body["reason"] == "与你当前的 AI 研发方向高度相关"
    assert body["priority"] == "high"


def test_opportunity_client_cannot_override_snapshot(client):
    _seed_demo()
    response = client.post(
        "/api/discoveries",
        headers=_header(),
        json={
            "reference_type": "opportunity",
            "opportunity_id": str(DEMO_POLICY_ID),
            "title": "假的标题",
            "deadline": "2020-01-01",
        },
    )
    assert response.status_code == 422


def test_create_source_snapshots_fields(client):
    _seed_demo()
    response = client.post(
        "/api/discoveries",
        headers=_header(),
        json={
            "reference_type": "source",
            "source_id": str(DEMO_POLICY_SOURCE_OFFICIAL_ID),
            "reason": "这条内容可能包含与你相关的申报机会",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reference_type"] == "source"
    assert body["source_id"] == str(DEMO_POLICY_SOURCE_OFFICIAL_ID)
    assert body["opportunity_id"] is None
    assert body["title"] == "关于组织申报科技型企业研发创新支持专项的通知"
    assert body["issuer"] == "北京市科学技术委员会"
    assert body["reference_url"] == "https://example.beijing.gov.cn/rd-innovation-support"
    assert body["opportunity_type"] is None
    assert body["deadline"] is None


def test_source_title_fallback_ingestion_hostname_and_default(client):
    _seed_demo()
    db = SessionLocal()
    try:
        now = utc_now()
        ingested_source = OpportunitySource(
            source_type=SourceType.MEDIA_ARTICLE.value,
            title=None,
            publisher="某媒体",
            url="https://news.example.com/article",
            created_at=now,
            updated_at=now,
        )
        add_source(db, ingested_source)
        add_ingested_content(
            db,
            IngestedContent(
                source_id=ingested_source.id,
                input_type="url",
                fetch_status="success",
                extraction_status="success",
                raw_title="入库后的文章标题",
            ),
        )
        hostname_source = OpportunitySource(
            source_type=SourceType.MEDIA_ARTICLE.value,
            title=None,
            publisher=None,
            url="https://policy.example.org/path",
            created_at=now,
            updated_at=now,
        )
        add_source(db, hostname_source)
        fallback_source = OpportunitySource(
            source_type=SourceType.OTHER.value,
            title=None,
            publisher=None,
            url=None,
            created_at=now,
            updated_at=now,
        )
        add_source(db, fallback_source)
        db.commit()
        ingested_id = ingested_source.id
        hostname_id = hostname_source.id
        fallback_id = fallback_source.id
    finally:
        db.close()

    ingested = client.post(
        "/api/discoveries",
        headers=_header(),
        json={"reference_type": "source", "source_id": str(ingested_id)},
    )
    assert ingested.status_code == 201
    assert ingested.json()["title"] == "入库后的文章标题"

    hostname = client.post(
        "/api/discoveries",
        headers=_header(),
        json={"reference_type": "source", "source_id": str(hostname_id)},
    )
    assert hostname.status_code == 201
    assert hostname.json()["title"] == "policy.example.org"

    fallback = client.post(
        "/api/discoveries",
        headers=_header(),
        json={"reference_type": "source", "source_id": str(fallback_id)},
    )
    assert fallback.status_code == 201
    assert fallback.json()["title"] == "内容发现"


def test_invalid_reference_combinations_are_rejected(client):
    _seed_demo()
    manual_with_opportunity = client.post(
        "/api/discoveries",
        headers=_header(),
        json={
            "reference_type": "manual",
            "title": "不应携带引用",
            "opportunity_id": str(DEMO_POLICY_ID),
        },
    )
    assert manual_with_opportunity.status_code == 422

    opportunity_with_source = client.post(
        "/api/discoveries",
        headers=_header(),
        json={
            "reference_type": "opportunity",
            "opportunity_id": str(DEMO_POLICY_ID),
            "source_id": str(DEMO_POLICY_SOURCE_OFFICIAL_ID),
        },
    )
    assert opportunity_with_source.status_code == 422

    missing_opportunity = client.post(
        "/api/discoveries",
        headers=_header(),
        json={"reference_type": "opportunity", "opportunity_id": str(uuid4())},
    )
    assert missing_opportunity.status_code == 404
    assert missing_opportunity.json()["error"]["code"] == "OPPORTUNITY_NOT_FOUND"

    missing_source = client.post(
        "/api/discoveries",
        headers=_header(),
        json={"reference_type": "source", "source_id": str(uuid4())},
    )
    assert missing_source.status_code == 404
    assert missing_source.json()["error"]["code"] == "SOURCE_NOT_FOUND"


def test_discovery_apis_require_identity(client):
    created = _create_manual(client)
    discovery_id = created.json()["id"]
    endpoints = [
        ("post", "/api/discoveries", {"reference_type": "manual", "title": "无身份"}),
        ("get", "/api/discoveries", None),
        ("get", f"/api/discoveries/{discovery_id}", None),
        ("post", f"/api/discoveries/{discovery_id}/withdraw", None),
    ]
    for method, path, json_body in endpoints:
        kwargs = {} if json_body is None else {"json": json_body}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "DEV_IDENTITY_REQUIRED"


def test_enterprise_isolation_for_detail_list_and_withdraw(client):
    created = _create_manual(client)
    discovery_id = created.json()["id"]
    other_user_id = _seed_other_identity()

    detail = client.get(f"/api/discoveries/{discovery_id}", headers=_header(other_user_id))
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "DISCOVERY_NOT_FOUND"

    listing = client.get("/api/discoveries", headers=_header(other_user_id))
    assert listing.status_code == 200
    assert listing.json()["items"] == []

    withdraw = client.post(
        f"/api/discoveries/{discovery_id}/withdraw",
        headers=_header(other_user_id),
    )
    assert withdraw.status_code == 404
    assert withdraw.json()["error"]["code"] == "DISCOVERY_NOT_FOUND"
    assert _get_item(discovery_id).status == DiscoveryStatus.ACTIVE.value


def test_list_defaults_to_active_and_supports_withdrawn_filter(client):
    active = _create_manual(client, title="有效发现")
    withdrawn = _create_manual(client, title="已撤回发现")
    withdraw = client.post(
        f"/api/discoveries/{withdrawn.json()['id']}/withdraw",
        headers=_header(),
    )
    assert withdraw.status_code == 200
    assert withdraw.json()["status"] == "withdrawn"
    assert withdraw.json()["withdrawn_at"]

    default_list = client.get("/api/discoveries", headers=_header())
    assert default_list.status_code == 200
    ids = [item["id"] for item in default_list.json()["items"]]
    assert active.json()["id"] in ids
    assert withdrawn.json()["id"] not in ids

    withdrawn_list = client.get("/api/discoveries?status=withdrawn", headers=_header())
    withdrawn_ids = [item["id"] for item in withdrawn_list.json()["items"]]
    assert withdrawn.json()["id"] in withdrawn_ids
    assert active.json()["id"] not in withdrawn_ids


def test_list_orders_by_priority_then_created_at(client):
    _seed_demo()
    normal_old = _create_manual(client, title="normal old", priority="normal")
    high_old = _create_manual(client, title="high old", priority="high")
    low_newest = _create_manual(client, title="low newest", priority="low")
    high_newest = _create_manual(client, title="high newest", priority="high")
    db = SessionLocal()
    try:
        base = utc_now()
        mapping = {
            normal_old.json()["id"]: base,
            high_old.json()["id"]: base + timedelta(seconds=1),
            low_newest.json()["id"]: base + timedelta(seconds=10),
            high_newest.json()["id"]: base + timedelta(seconds=11),
        }
        for item_id, created_at in mapping.items():
            row = db.get(DiscoveryItem, UUID(item_id))
            assert row is not None
            row.created_at = created_at
            db.add(row)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/discoveries", headers=_header())
    titles = [item["title"] for item in response.json()["items"]]
    assert titles[:4] == ["high newest", "high old", "normal old", "low newest"]


def test_withdraw_is_idempotent(client):
    created = _create_manual(client)
    discovery_id = created.json()["id"]
    first = client.post(f"/api/discoveries/{discovery_id}/withdraw", headers=_header())
    second = client.post(f"/api/discoveries/{discovery_id}/withdraw", headers=_header())
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "withdrawn"
    assert second.json()["id"] == discovery_id
    db = SessionLocal()
    try:
        count = db.scalar(select(func.count()).select_from(DiscoveryItem))
        assert int(count or 0) == 1
    finally:
        db.close()


def test_reference_delete_keeps_discovery_snapshot(client):
    _seed_demo()
    created = client.post(
        "/api/discoveries",
        headers=_header(),
        json={
            "reference_type": "opportunity",
            "opportunity_id": str(DEMO_POLICY_ID),
            "reason": "snapshot 应在引用删除后保留",
        },
    )
    assert created.status_code == 201
    discovery_id = created.json()["id"]

    db = SessionLocal()
    try:
        opportunity = db.get(Opportunity, DEMO_POLICY_ID)
        assert opportunity is not None
        db.delete(opportunity)
        db.commit()
    finally:
        db.close()

    detail = client.get(f"/api/discoveries/{discovery_id}", headers=_header())
    assert detail.status_code == 200
    body = detail.json()
    assert body["opportunity_id"] is None
    assert body["reference_type"] == "opportunity"
    assert body["title"] == "北京市科技型企业研发创新支持专项"
    assert body["deadline"] == "2026-10-15"
    assert _get_item(discovery_id).title == "北京市科技型企业研发创新支持专项"


def test_no_notification_or_user_feedback_state(client):
    response = _create_manual(client)
    assert response.status_code == 201
    columns = {column.name for column in DiscoveryItem.__table__.columns}
    assert "seen_at" not in columns
    assert "saved_at" not in columns
    assert "dismissed_at" not in columns
    assert "deprioritized_at" not in columns
    assert {item.value for item in DiscoveryStatus} == {"active", "withdrawn"}
    assert "notifications" not in Base.metadata.tables
    assert "notify" not in Base.metadata.tables
    assert not any("websocket" in name for name in Base.metadata.tables)


def test_existing_contracts_remain_compatible(client):
    _seed_demo()
    me = client.get("/api/me", headers=_header())
    assert me.status_code == 200
    ingest = client.post(
        "/api/content/ingest",
        json={"content_type": "text", "content": "无需身份即可接入的回归正文，长度足够。"},
    )
    assert ingest.status_code == 201
    submission = client.post(
        "/api/user-submissions",
        headers=_header(),
        json={"input_type": "text", "content": "回归提交正文需要足够长度。"},
    )
    assert submission.status_code == 201
    assert submission.json()["status"] == "pending"


def test_openapi_discovery_routes_require_dev_identity(client):
    payload = client.get("/openapi.json").json()
    paths = payload["paths"]
    expected = {
        "/api/discoveries": ["post", "get"],
        "/api/discoveries/{discovery_id}": ["get"],
        "/api/discoveries/{discovery_id}/withdraw": ["post"],
        "/api/discoveries/{discovery_id}/accept": ["post"],
    }
    for path, methods in expected.items():
        assert path in paths
        for method in methods:
            parameters = paths[path][method].get("parameters", [])
            header = next(item for item in parameters if item.get("name") == "X-Dev-User-Id")
            assert header["in"] == "header"
    schemas = payload["components"]["schemas"]
    assert "CreateOpportunityDiscoveryRequest" in schemas
    assert "CreateSourceDiscoveryRequest" in schemas
    assert "CreateManualDiscoveryRequest" in schemas
    assert "DiscoveryItemSummary" in schemas
    assert "DiscoveryItemDetail" in schemas
    assert schemas["CreateManualDiscoveryRequest"].get("additionalProperties") is False
