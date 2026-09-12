from uuid import uuid4

from app.domains.enterprise.seed import DEMO_ENTERPRISE_ID, seed_demo_enterprise
from app.core.database import SessionLocal


def _create_enterprise(client, name: str = "测试企业"):
    response = client.post(
        "/api/enterprises",
        json={
            "name": name,
            "registration_region": "北京市海淀区",
            "established_at": "2020-01-15",
            "enterprise_type": "technology_startup",
            "industry": "enterprise_software",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_state(client, enterprise_id: str, effective_at: str, product_stage: str = "demo"):
    response = client.post(
        f"/api/enterprises/{enterprise_id}/states",
        json={
            "product_stage": product_stage,
            "business_stage": "pre_revenue",
            "team_size": 4,
            "revenue_stage": "no_revenue",
            "funding_stage": "bootstrapped",
            "ip_count": None,
            "qualifications": ["科技型中小企业"],
            "current_goal": "获得首批真实场景验证",
            "current_constraint": "缺少可规模化验证案例",
            "recent_events": ["产品 Demo 已完成"],
            "available_materials": ["营业执照", "企业简介"],
            "effective_at": effective_at,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_list_enterprises(client):
    created = _create_enterprise(client)
    response = client.get("/api/enterprises")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["id"] == created["id"]
    assert items[0]["name"] == "测试企业"
    assert items[0]["registration_region"] == "北京市海淀区"
    assert items[0]["enterprise_type"] == "technology_startup"
    assert items[0]["industry"] == "enterprise_software"


def test_get_enterprise(client):
    created = _create_enterprise(client, name="详情企业")
    response = client.get(f"/api/enterprises/{created['id']}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == created["id"]
    assert payload["name"] == "详情企业"
    assert payload["established_at"] == "2020-01-15"
    assert payload["created_at"].endswith("Z")
    assert payload["updated_at"].endswith("Z")


def test_get_enterprise_not_found(client):
    response = client.get(f"/api/enterprises/{uuid4()}")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "ENTERPRISE_NOT_FOUND"
    assert error["message"] == "Enterprise not found"


def test_get_latest_enterprise_state(client):
    created = _create_enterprise(client)
    _create_state(
        client,
        created["id"],
        effective_at="2026-01-01T00:00:00Z",
        product_stage="prototype",
    )
    latest = _create_state(
        client,
        created["id"],
        effective_at="2026-08-01T00:00:00Z",
        product_stage="product_validation",
    )
    response = client.get(f"/api/enterprises/{created['id']}/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == latest["id"]
    assert payload["product_stage"] == "product_validation"
    assert payload["business_stage"] == "pre_revenue"
    assert payload["team_size"] == 4
    assert payload["revenue_stage"] == "no_revenue"
    assert payload["funding_stage"] == "bootstrapped"
    assert payload["ip_count"] is None
    assert payload["qualifications"] == ["科技型中小企业"]
    assert payload["current_goal"] == "获得首批真实场景验证"
    assert payload["current_constraint"] == "缺少可规模化验证案例"
    assert payload["recent_events"] == ["产品 Demo 已完成"]
    assert payload["available_materials"] == ["营业执照", "企业简介"]
    assert payload["effective_at"].endswith("Z")


def test_enterprise_state_not_found(client):
    created = _create_enterprise(client)
    response = client.get(f"/api/enterprises/{created['id']}/state")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "ENTERPRISE_STATE_NOT_FOUND"


def test_create_enterprise(client):
    payload = _create_enterprise(client, name="新建企业")
    assert payload["name"] == "新建企业"
    assert payload["enterprise_type"] == "technology_startup"


def test_create_enterprise_state(client):
    created = _create_enterprise(client)
    state = _create_state(client, created["id"], "2026-09-01T12:00:00Z")
    assert state["enterprise_id"] == created["id"]
    assert state["product_stage"] == "demo"


def test_seed_demo_enterprise_is_idempotent(client):
    db = SessionLocal()
    try:
        first = seed_demo_enterprise(db)
        second = seed_demo_enterprise(db)
        assert first.id == DEMO_ENTERPRISE_ID
        assert second.id == DEMO_ENTERPRISE_ID
        assert first.id == second.id
    finally:
        db.close()

    response = client.get("/api/enterprises")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["id"] == str(DEMO_ENTERPRISE_ID)
    assert items[0]["name"] == "筑脉科技"

    state = client.get(f"/api/enterprises/{DEMO_ENTERPRISE_ID}/state")
    assert state.status_code == 200
    payload = state.json()
    assert payload["product_stage"] == "product_validation"
    assert payload["ip_count"] == 3
