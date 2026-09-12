from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domains.intelligence.contracts import (
    DEFAULT_ANALYZER_VERSION,
    EVIDENCE_TEXT_MAX_CHARS,
    SCHEMA_VERSION,
    forbidden_fields_present,
)
from app.domains.intelligence.enums import (
    ApparentSourceType,
    IntermediaryLevel,
    MarketingLevel,
    OpportunityRelevance,
)
from app.domains.intelligence.schemas import (
    ClaimedRequirement,
    ContentIntelligenceInput,
    ContentIntelligenceResult,
    IntelligenceAnalysis,
    IntelligenceEvidence,
    IntelligenceMetadata,
    OpportunityClaim,
    SourceAssessment,
)
from app.domains.opportunity.enums import RequirementOperator

FIXTURES = Path(__file__).parent / "fixtures" / "intelligence"


def _load_result(name: str) -> ContentIntelligenceResult:
    return ContentIntelligenceResult.model_validate_json(
        (FIXTURES / name).read_text(encoding="utf-8")
    )


def test_content_intelligence_result_valid():
    result = _load_result("official_like_opportunity.json")
    assert result.analysis.content_nature.value == "opportunity_announcement"
    assert result.source_assessment.apparent_source_type == ApparentSourceType.OFFICIAL_LIKE
    assert result.opportunity_claim is not None
    assert result.opportunity_claim.claimed_title == "北京市科技型企业研发创新支持专项"
    assert result.metadata.schema_version == SCHEMA_VERSION
    assert forbidden_fields_present(result.model_dump(mode="json")) == set()


def test_confidence_range_validation():
    with pytest.raises(ValidationError):
        IntelligenceAnalysis(
            content_nature="unknown",
            opportunity_relevance="unknown",
            confidence=1.5,
        )
    with pytest.raises(ValidationError):
        IntelligenceAnalysis(
            content_nature="unknown",
            opportunity_relevance="unknown",
            confidence=-0.1,
        )


def test_opportunity_claim_can_be_null():
    result = _load_result("general_information.json")
    assert result.analysis.opportunity_relevance == OpportunityRelevance.NONE
    assert result.opportunity_claim is None


def test_marketing_content_can_have_opportunity_claim():
    result = _load_result("marketing_opportunity.json")
    assert result.source_assessment.marketing_level == MarketingLevel.HIGH
    assert result.analysis.opportunity_relevance == OpportunityRelevance.HIGH
    assert result.opportunity_claim is not None
    assert result.opportunity_claim.claimed_title is not None


def test_intermediary_is_not_verification():
    result = _load_result("service_provider_opportunity.json")
    payload = result.model_dump(mode="json")
    assert result.source_assessment.intermediary_level == IntermediaryLevel.LIKELY
    assert result.opportunity_claim is not None
    assert "verified" not in payload
    assert "is_official" not in payload
    assert forbidden_fields_present(payload) == set()


def test_evidence_reference():
    result = _load_result("official_like_opportunity.json")
    assert result.opportunity_claim is not None
    requirement = result.opportunity_claim.claimed_requirements[0]
    evidence_ids = {item.id for item in result.evidence}
    assert set(requirement.evidence_ids) <= evidence_ids


def test_claimed_requirement_validation():
    with pytest.raises(ValidationError):
        ClaimedRequirement(
            key="",
            label="地区",
            operator=RequirementOperator.EQUALS,
            confidence=0.5,
        )


def test_json_serialization():
    result = _load_result("official_like_opportunity.json")
    payload = result.model_dump(mode="json")
    restored = ContentIntelligenceResult.model_validate(payload)
    assert restored.opportunity_claim is not None
    assert restored.opportunity_claim.claimed_deadline.isoformat() == "2026-10-15"
    assert restored.metadata.created_at.tzinfo is not None


def test_schema_version_present():
    result = _load_result("official_like_opportunity.json")
    assert result.metadata.schema_version == "1.0"
    assert result.metadata.analyzer_version == DEFAULT_ANALYZER_VERSION


def test_evidence_text_length_limit():
    with pytest.raises(ValidationError):
        IntelligenceEvidence(
            id="ev_too_long",
            kind="direct_quote",
            text="字" * (EVIDENCE_TEXT_MAX_CHARS + 1),
        )


def test_blank_normalized_text_rejected():
    with pytest.raises(ValidationError):
        ContentIntelligenceInput(
            source_id=uuid4(),
            ingestion_id=uuid4(),
            normalized_text="   ",
        )


def test_unknown_evidence_id_rejected():
    with pytest.raises(ValidationError):
        ContentIntelligenceResult(
            analysis=IntelligenceAnalysis(
                content_nature="general_information",
                opportunity_relevance="high",
                confidence=0.5,
            ),
            source_assessment=SourceAssessment(
                apparent_source_type="unknown",
                marketing_level="unknown",
                intermediary_level="unknown",
                originality_claim="unclear",
            ),
            opportunity_claim=OpportunityClaim(
                claim_confidence=0.5,
                claimed_requirements=[
                    ClaimedRequirement(
                        key="region",
                        label="地区",
                        operator=RequirementOperator.EQUALS,
                        confidence=0.5,
                        evidence_ids=["ev_missing"],
                    )
                ],
            ),
            evidence=[],
            metadata=IntelligenceMetadata(
                created_at=datetime(2026, 9, 12, 11, 0, tzinfo=UTC),
            ),
        )


def test_all_contract_fixtures_load():
    for name in (
        "official_like_opportunity.json",
        "marketing_opportunity.json",
        "service_provider_opportunity.json",
        "general_information.json",
    ):
        result = _load_result(name)
        assert result.metadata.schema_version == SCHEMA_VERSION
        assert forbidden_fields_present(result.model_dump(mode="json")) == set()
