from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.domains.opportunity.models import OpportunityRequirement, OpportunitySource
from app.domains.opportunity.seed import (
    DEMO_POLICY_ID,
    DEMO_UNMAPPED_SOURCE_ID,
    seed_demo_opportunities,
)


def _create_opportunity(client, title: str = "测试机会"):
    response = client.post(
        "/api/opportunities",
        json={
            "type": "policy",
            "title": title,
            "issuer": "测试发布方",
            "region": "北京市",
            "publish_date": "2026-06-01",
            "deadline": "2026-10-15",
            "status": "active",
            "summary": "用于测试的规范机会。",
            "resource_value": {"funding": "最高10万元"},
            "required_materials": ["营业执照"],
            "application_process": ["在线申报"],
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_source(client, opportunity_id: str | None, title: str, source_type: str = "wechat_article"):
    payload = {
        "source_type": source_type,
        "title": title,
        "publisher": "测试发布者",
        "content_excerpt": "摘要片段",
    }
    if opportunity_id is None:
        response = client.post("/api/opportunity-sources", json=payload)
    else:
        response = client.post(f"/api/opportunities/{opportunity_id}/sources", json=payload)
    assert response.status_code == 201
    return response.json()


def test_list_opportunities(client):
    first = _create_opportunity(client, "政策机会")
    client.post(
        "/api/opportunities",
        json={
            "type": "scenario",
            "title": "场景机会",
            "status": "active",
        },
    )
    response = client.get("/api/opportunities")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert {item["type"] for item in items} == {"policy", "scenario"}
    assert "sources" not in items[0]
    assert "requirements" not in items[0]

    filtered = client.get("/api/opportunities", params={"type": "policy"})
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["id"] == first["id"]


def test_get_opportunity(client):
    created = _create_opportunity(client, "详情机会")
    response = client.get(f"/api/opportunities/{created['id']}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "详情机会"
    assert payload["issuer"] == "测试发布方"
    assert payload["sources"] == []
    assert payload["requirements"] == []
    assert payload["created_at"].endswith("Z")


def test_get_opportunity_not_found(client):
    response = client.get(f"/api/opportunities/{uuid4()}")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "OPPORTUNITY_NOT_FOUND"


def test_create_opportunity(client):
    payload = _create_opportunity(client, "新建机会")
    assert payload["title"] == "新建机会"
    assert payload["type"] == "policy"
    assert payload["status"] == "active"


def test_get_opportunity_sources(client):
    created = _create_opportunity(client)
    _create_source(client, created["id"], "来源一", "official_document")
    response = client.get(f"/api/opportunities/{created['id']}/sources")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "来源一"


def test_add_opportunity_source(client):
    created = _create_opportunity(client)
    source = _create_source(client, created["id"], "已映射来源", "official_news")
    assert source["opportunity_id"] == created["id"]
    detail = client.get(f"/api/opportunities/{created['id']}")
    assert len(detail.json()["sources"]) == 1


def test_create_unmapped_source(client):
    source = _create_source(client, None, "最高补贴500万，北京科技企业别错过！")
    assert source["opportunity_id"] is None
    assert source["source_type"] == "wechat_article"


def test_get_requirements(client):
    created = _create_opportunity(client)
    client.post(
        f"/api/opportunities/{created['id']}/requirements",
        json={
            "key": "registration_region",
            "label": "企业注册地区",
            "operator": "equals",
            "expected_value": "北京市",
            "required": True,
        },
    )
    response = client.get(f"/api/opportunities/{created['id']}/requirements")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["key"] == "registration_region"


def test_add_requirement(client):
    created = _create_opportunity(client)
    response = client.post(
        f"/api/opportunities/{created['id']}/requirements",
        json={
            "key": "ip_count",
            "label": "知识产权数量",
            "operator": "gte",
            "expected_value": 3,
            "required": True,
            "description": "发明专利数量不少于3项。",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["key"] == "ip_count"
    assert payload["operator"] == "gte"
    assert payload["expected_value"] == 3


def test_source_can_exist_without_opportunity(client):
    source = client.post(
        "/api/opportunity-sources",
        json={
            "source_type": "wechat_article",
            "title": "尚未识别的外部内容",
            "publisher": "XX企业服务",
        },
    )
    assert source.status_code == 201
    assert source.json()["opportunity_id"] is None


def test_opportunity_can_have_multiple_sources(client):
    created = _create_opportunity(client)
    _create_source(client, created["id"], "官方通知", "official_document")
    _create_source(client, created["id"], "公众号转载", "official_wechat")
    _create_source(client, created["id"], "服务机构文章", "service_provider")
    response = client.get(f"/api/opportunities/{created['id']}/sources")
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_deleting_opportunity_sets_source_null_and_cascades_requirements():
    created_id = None
    source_id = None
    db = SessionLocal()
    try:
        from app.domains.opportunity.models import Opportunity
        from app.domains.opportunity.schemas import (
            OpportunityCreate,
            OpportunityRequirementCreate,
            OpportunitySourceCreate,
        )
        from app.domains.opportunity.enums import (
            OpportunityStatus,
            OpportunityType,
            RequirementOperator,
            SourceType,
        )
        from app.domains.opportunity import service

        opportunity = service.create_opportunity(
            db,
            OpportunityCreate(
                type=OpportunityType.POLICY,
                title="删除策略测试",
                status=OpportunityStatus.ACTIVE,
            ),
        )
        created_id = opportunity.id
        source = service.create_source(
            db,
            OpportunitySourceCreate(
                source_type=SourceType.MEDIA_ARTICLE,
                title="外部证据",
            ),
            opportunity_id=created_id,
        )
        source_id = source.id
        service.create_requirement(
            db,
            created_id,
            OpportunityRequirementCreate(
                key="registration_region",
                label="注册地区",
                operator=RequirementOperator.EQUALS,
                expected_value="北京市",
            ),
        )
        db.delete(db.get(Opportunity, created_id))
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        source = db.get(OpportunitySource, source_id)
        assert source is not None
        assert source.opportunity_id is None
        remaining = list(
            db.scalars(
                select(OpportunityRequirement).where(
                    OpportunityRequirement.opportunity_id == created_id
                )
            ).all()
        )
        assert remaining == []
    finally:
        db.close()


def test_seed_demo_opportunities_is_idempotent(client):
    db = SessionLocal()
    try:
        first = seed_demo_opportunities(db)
        second = seed_demo_opportunities(db)
        assert len(first) == 4
        assert {item.id for item in first} == {item.id for item in second}
    finally:
        db.close()

    items = client.get("/api/opportunities").json()
    types = {item["type"] for item in items}
    assert types >= {"policy", "competition", "financial_service", "scenario"}
    assert len(items) == 4

    sources = client.get(f"/api/opportunities/{DEMO_POLICY_ID}/sources").json()
    assert len(sources) == 3

    unmapped = SessionLocal()
    try:
        source = unmapped.get(OpportunitySource, DEMO_UNMAPPED_SOURCE_ID)
        assert source is not None
        assert source.opportunity_id is None
    finally:
        unmapped.close()
