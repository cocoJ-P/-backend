"""Idempotent Demo Opportunity seed data.

All records are hand-written. This seed does not scrape, search, or call LLM.
"""

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domains.opportunity.enums import (
    OpportunityStatus,
    OpportunityType,
    RequirementOperator,
    SourceType,
)
from app.domains.opportunity.models import (
    Opportunity,
    OpportunityRequirement,
    OpportunitySource,
)
from app.domains.opportunity.repository import (
    add_opportunity,
    add_requirement,
    add_source,
    get_requirement,
    get_source,
)

DEMO_POLICY_ID = UUID("21a1c0de-0001-4b01-8a01-000000000001")
DEMO_COMPETITION_ID = UUID("21a1c0de-0002-4b02-8a02-000000000002")
DEMO_FINANCIAL_ID = UUID("21a1c0de-0003-4b03-8a03-000000000003")
DEMO_SCENARIO_ID = UUID("21a1c0de-0004-4b04-8a04-000000000004")
DEMO_UNMAPPED_SOURCE_ID = UUID("21a1c0de-0099-4b99-8a99-000000000099")

DEMO_POLICY_SOURCE_OFFICIAL_ID = UUID("21a1c0de-0001-4b01-8a01-000000000011")
DEMO_POLICY_SOURCE_WECHAT_ID = UUID("21a1c0de-0001-4b01-8a01-000000000012")
DEMO_POLICY_SOURCE_PROVIDER_ID = UUID("21a1c0de-0001-4b01-8a01-000000000013")


def seed_demo_opportunities(db: Session) -> list[Opportunity]:
    now = utc_now()
    policy = _upsert_opportunity(
        db,
        opportunity_id=DEMO_POLICY_ID,
        now=now,
        type=OpportunityType.POLICY.value,
        title="北京市科技型企业研发创新支持专项",
        issuer="北京市科学技术委员会",
        region="北京市",
        publish_date=date(2026, 6, 1),
        deadline=date(2026, 10, 15),
        status=OpportunityStatus.ACTIVE.value,
        official_url="https://example.beijing.gov.cn/rd-innovation-support",
        summary="支持科技型企业持续加大研发投入，对符合条件的研发项目给予资金支持。",
        resource_value={"funding": "最高100万元", "industry_connection": True},
        required_materials=["营业执照", "企业简介", "项目申报书", "知识产权证明"],
        application_process=["在线申报", "资格审核", "专家评审", "结果公示"],
    )
    _upsert_source(
        db,
        source_id=DEMO_POLICY_SOURCE_OFFICIAL_ID,
        now=now,
        opportunity_id=DEMO_POLICY_ID,
        source_type=SourceType.OFFICIAL_DOCUMENT.value,
        title="关于组织申报科技型企业研发创新支持专项的通知",
        publisher="北京市科学技术委员会",
        url="https://example.beijing.gov.cn/rd-innovation-support",
        published_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        content_excerpt="北京市科学技术委员会现组织申报科技型企业研发创新支持专项。",
    )
    _upsert_source(
        db,
        source_id=DEMO_POLICY_SOURCE_WECHAT_ID,
        now=now,
        opportunity_id=DEMO_POLICY_ID,
        source_type=SourceType.OFFICIAL_WECHAT.value,
        title="市科委通知：研发创新支持专项开始申报",
        publisher="北京科技",
        url="https://mp.weixin.qq.com/example-official-repost",
        published_at=datetime(2026, 6, 2, 3, 0, tzinfo=timezone.utc),
        content_excerpt="北京市科委发布研发创新支持专项申报通知，原文见政府网站。",
    )
    _upsert_source(
        db,
        source_id=DEMO_POLICY_SOURCE_PROVIDER_ID,
        now=now,
        opportunity_id=DEMO_POLICY_ID,
        source_type=SourceType.SERVICE_PROVIDER.value,
        title="最高补贴100万！科技企业申报指南来了",
        publisher="XX企业服务",
        url="https://mp.weixin.qq.com/example-service-provider",
        published_at=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
        content_excerpt="代写材料、包过申报，名额有限，立即咨询。",
    )
    _upsert_requirement(
        db,
        requirement_id=UUID("21a1c0de-0001-4b01-8a01-000000000021"),
        opportunity_id=DEMO_POLICY_ID,
        key="registration_region",
        label="企业注册地区",
        operator=RequirementOperator.EQUALS.value,
        expected_value="北京市",
        required=True,
        description="企业注册地应位于北京市行政区域内。",
        source_reference="申报通知第三条第1款",
    )
    _upsert_requirement(
        db,
        requirement_id=UUID("21a1c0de-0001-4b01-8a01-000000000022"),
        opportunity_id=DEMO_POLICY_ID,
        key="enterprise_type",
        label="企业类型",
        operator=RequirementOperator.IN.value,
        expected_value=["technology_startup", "科技型企业"],
        required=True,
        description="申报主体应为科技型企业。",
        source_reference="申报通知第三条第2款",
    )
    _upsert_requirement(
        db,
        requirement_id=UUID("21a1c0de-0001-4b01-8a01-000000000023"),
        opportunity_id=DEMO_POLICY_ID,
        key="rd_spending",
        label="研发投入",
        operator=RequirementOperator.MANUAL_REVIEW.value,
        expected_value=None,
        required=False,
        description="研发投入需结合申报材料人工审核。",
        source_reference="申报通知第四条",
    )

    competition = _upsert_opportunity(
        db,
        opportunity_id=DEMO_COMPETITION_ID,
        now=now,
        type=OpportunityType.COMPETITION.value,
        title="产业创新应用大赛",
        issuer="北京市相关主管部门",
        region="北京市",
        publish_date=date(2026, 5, 15),
        deadline=date(2026, 10, 8),
        status=OpportunityStatus.ACTIVE.value,
        official_url=None,
        summary="面向产业创新应用项目的赛事，优秀项目可获得场景对接与奖金支持。",
        resource_value={"award": "奖金与场景对接", "scenario": True},
        required_materials=["营业执照", "项目介绍", "团队简历"],
        application_process=["在线报名", "初赛路演", "决赛评审"],
    )
    _upsert_source(
        db,
        source_id=UUID("21a1c0de-0002-4b02-8a02-000000000011"),
        now=now,
        opportunity_id=DEMO_COMPETITION_ID,
        source_type=SourceType.OFFICIAL_NEWS.value,
        title="产业创新应用大赛开始报名",
        publisher="北京市相关主管部门",
        url=None,
        published_at=datetime(2026, 5, 15, 8, 0, tzinfo=timezone.utc),
        content_excerpt="大赛面向产业创新应用项目开放报名。",
    )
    _upsert_requirement(
        db,
        requirement_id=UUID("21a1c0de-0002-4b02-8a02-000000000021"),
        opportunity_id=DEMO_COMPETITION_ID,
        key="industry",
        label="所属行业",
        operator=RequirementOperator.CONTAINS.value,
        expected_value="产业应用",
        required=False,
        description="优先支持具有产业落地能力的创新应用项目。",
        source_reference="赛事章程第三条",
    )

    financial = _upsert_opportunity(
        db,
        opportunity_id=DEMO_FINANCIAL_ID,
        now=now,
        type=OpportunityType.FINANCIAL_SERVICE.value,
        title="科技型中小企业贷款贴息备案",
        issuer="北京市地方金融管理部门",
        region="北京市",
        publish_date=date(2026, 7, 1),
        deadline=date(2026, 11, 20),
        status=OpportunityStatus.ACTIVE.value,
        official_url=None,
        summary="对符合条件的科技型中小企业贷款利息给予贴息支持。",
        resource_value={"funding": "贷款贴息", "industry_connection": False},
        required_materials=["营业执照", "贷款合同", "利息凭证"],
        application_process=["在线备案", "资料核验", "贴息拨付"],
    )
    _upsert_source(
        db,
        source_id=UUID("21a1c0de-0003-4b03-8a03-000000000011"),
        now=now,
        opportunity_id=DEMO_FINANCIAL_ID,
        source_type=SourceType.OFFICIAL_DOCUMENT.value,
        title="科技型中小企业贷款贴息备案指引",
        publisher="北京市地方金融管理部门",
        url=None,
        published_at=datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc),
        content_excerpt="符合条件的科技型中小企业可申请贷款贴息备案。",
    )
    _upsert_requirement(
        db,
        requirement_id=UUID("21a1c0de-0003-4b03-8a03-000000000021"),
        opportunity_id=DEMO_FINANCIAL_ID,
        key="qualification",
        label="企业资质",
        operator=RequirementOperator.CONTAINS.value,
        expected_value="科技型中小企业",
        required=True,
        description="申报主体应具备科技型中小企业相关资质。",
        source_reference="备案指引第二条",
    )

    scenario = _upsert_opportunity(
        db,
        opportunity_id=DEMO_SCENARIO_ID,
        now=now,
        type=OpportunityType.SCENARIO.value,
        title="2026年北京市人工智能产业应用场景开放计划",
        issuer="北京市科学技术委员会",
        region="北京市",
        publish_date=date(2026, 4, 10),
        deadline=date(2026, 9, 30),
        status=OpportunityStatus.ACTIVE.value,
        official_url="https://example.beijing.gov.cn/ai-scenario-2026",
        summary="面向人工智能企业开放真实应用场景，支持产品验证与规模化落地。",
        resource_value={"scenario": True, "industry_connection": True, "funding": "场景合作"},
        required_materials=["营业执照", "产品介绍", "场景方案"],
        application_process=["提交方案", "场景对接", "试点实施"],
    )
    _upsert_source(
        db,
        source_id=UUID("21a1c0de-0004-4b04-8a04-000000000011"),
        now=now,
        opportunity_id=DEMO_SCENARIO_ID,
        source_type=SourceType.OFFICIAL_DOCUMENT.value,
        title="北京市人工智能产业应用场景开放计划申报通知",
        publisher="北京市科学技术委员会",
        url="https://example.beijing.gov.cn/ai-scenario-2026",
        published_at=datetime(2026, 4, 10, 8, 0, tzinfo=timezone.utc),
        content_excerpt="面向人工智能企业开放真实产业应用场景。",
    )
    _upsert_requirement(
        db,
        requirement_id=UUID("21a1c0de-0004-4b04-8a04-000000000021"),
        opportunity_id=DEMO_SCENARIO_ID,
        key="industry",
        label="所属行业",
        operator=RequirementOperator.IN.value,
        expected_value=["artificial_intelligence", "人工智能"],
        required=True,
        description="申报主体应为人工智能相关企业。",
        source_reference="申报通知第二条",
    )
    _upsert_requirement(
        db,
        requirement_id=UUID("21a1c0de-0004-4b04-8a04-000000000022"),
        opportunity_id=DEMO_SCENARIO_ID,
        key="ip_count",
        label="知识产权数量",
        operator=RequirementOperator.GTE.value,
        expected_value=1,
        required=False,
        description="优先支持已具备相关知识产权的企业。",
        source_reference="申报通知第三条",
    )

    _upsert_source(
        db,
        source_id=DEMO_UNMAPPED_SOURCE_ID,
        now=now,
        opportunity_id=None,
        source_type=SourceType.WECHAT_ARTICLE.value,
        title="最高补贴500万，北京科技企业别错过！",
        publisher="XX企业服务",
        url="https://mp.weixin.qq.com/example-unmapped",
        published_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        content_excerpt="某公众号营销文章，尚未识别其对应的真实 Opportunity。",
    )

    db.commit()
    return [policy, competition, financial, scenario]


def _upsert_opportunity(
    db: Session,
    *,
    opportunity_id: UUID,
    now: datetime,
    **fields: object,
) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        opportunity = Opportunity(id=opportunity_id, created_at=now, **fields)
        opportunity.updated_at = now
        add_opportunity(db, opportunity)
        return opportunity

    for key, value in fields.items():
        setattr(opportunity, key, value)
    opportunity.updated_at = now
    return opportunity


def _upsert_source(
    db: Session,
    *,
    source_id: UUID,
    now: datetime,
    **fields: object,
) -> OpportunitySource:
    source = get_source(db, source_id)
    if source is None:
        source = OpportunitySource(id=source_id, created_at=now, updated_at=now, **fields)
        add_source(db, source)
        return source

    for key, value in fields.items():
        setattr(source, key, value)
    source.updated_at = now
    return source


def _upsert_requirement(
    db: Session,
    *,
    requirement_id: UUID,
    **fields: object,
) -> OpportunityRequirement:
    requirement = get_requirement(db, requirement_id)
    if requirement is None:
        requirement = OpportunityRequirement(id=requirement_id, **fields)
        add_requirement(db, requirement)
        return requirement

    for key, value in fields.items():
        setattr(requirement, key, value)
    return requirement
