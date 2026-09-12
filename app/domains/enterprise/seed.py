"""Idempotent Demo Enterprise seed data for 筑脉查查."""

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domains.enterprise.enums import (
    BusinessStage,
    EnterpriseType,
    FundingStage,
    ProductStage,
    RevenueStage,
)
from app.domains.enterprise.models import Enterprise, EnterpriseState
from app.domains.enterprise.repository import add_enterprise, add_state, get_enterprise, get_latest_state

DEMO_ENTERPRISE_ID = UUID("8f3e2a10-6b4c-4d91-9e2a-1b7c4d5e6f70")
DEMO_STATE_EFFECTIVE_AT = datetime(2026, 9, 1, tzinfo=timezone.utc)


def seed_demo_enterprise(db: Session) -> Enterprise:
    enterprise = get_enterprise(db, DEMO_ENTERPRISE_ID)
    now = utc_now()
    if enterprise is None:
        enterprise = Enterprise(
            id=DEMO_ENTERPRISE_ID,
            name="筑脉科技",
            registration_region="北京市朝阳区",
            established_at=date(2021, 4, 1),
            enterprise_type=EnterpriseType.TECHNOLOGY_STARTUP.value,
            industry="artificial_intelligence",
            created_at=now,
            updated_at=now,
        )
        add_enterprise(db, enterprise)
    else:
        enterprise.name = "筑脉科技"
        enterprise.registration_region = "北京市朝阳区"
        enterprise.established_at = date(2021, 4, 1)
        enterprise.enterprise_type = EnterpriseType.TECHNOLOGY_STARTUP.value
        enterprise.industry = "artificial_intelligence"
        enterprise.updated_at = now

    state = get_latest_state(db, DEMO_ENTERPRISE_ID)
    if state is None:
        state = EnterpriseState(enterprise_id=DEMO_ENTERPRISE_ID)
        _apply_demo_state(state)
        add_state(db, state)
    else:
        _apply_demo_state(state)
    db.commit()
    db.refresh(enterprise)
    return enterprise


def _apply_demo_state(state: EnterpriseState) -> None:
    state.product_stage = ProductStage.PRODUCT_VALIDATION.value
    state.business_stage = BusinessStage.EARLY_REVENUE.value
    state.team_size = 12
    state.revenue_stage = RevenueStage.EARLY_REVENUE.value
    state.funding_stage = FundingStage.SEED.value
    state.ip_count = 3
    state.qualifications = ["科技型中小企业"]
    state.current_goal = "获得真实应用场景"
    state.current_constraint = "缺少可规模化验证案例"
    state.recent_events = ["产品 Demo 已完成"]
    state.available_materials = [
        "营业执照",
        "企业简介",
        "产品介绍",
        "团队简历",
        "BP",
    ]
    state.effective_at = DEMO_STATE_EFFECTIVE_AT
