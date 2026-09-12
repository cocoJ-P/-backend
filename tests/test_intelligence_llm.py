from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import settings
from app.domains.intelligence.contracts import forbidden_fields_present
from app.domains.intelligence.llm.analyzer import LLMIntelligenceAnalyzer
from app.domains.intelligence.llm.prompt_builder import build_system_prompt, build_user_prompt
from app.domains.intelligence.llm.prompts import INTELLIGENCE_PROMPT_VERSION
from app.domains.intelligence.rules.analyzer import RuleAnalyzer
from app.domains.intelligence.schemas import ContentIntelligenceInput, ContentIntelligenceResult
from app.integrations.llm.errors import (
    LLMProviderError,
    LLMRateLimitError,
    LLMSchemaValidationError,
    LLMTimeoutError,
)
from app.integrations.llm.factory import create_llm_provider
from app.integrations.llm.providers.fake import FakeLLMProvider
from app.integrations.llm.providers.openai_compatible import OpenAICompatibleProvider
from app.integrations.llm.schemas import LLMUsage

FIXTURES = Path(__file__).parent / "fixtures" / "intelligence" / "rules"
RULES = RuleAnalyzer()


def _payload(name: str, **kwargs) -> ContentIntelligenceInput:
    return ContentIntelligenceInput(
        source_id=uuid4(),
        ingestion_id=uuid4(),
        normalized_text=(FIXTURES / name).read_text(encoding="utf-8"),
        **kwargs,
    )


def _base_result() -> dict:
    return {
        "analysis": {
            "content_nature": "marketing_content",
            "opportunity_relevance": "high",
            "confidence": 0.82,
            "warnings": [],
        },
        "source_assessment": {
            "apparent_source_type": "service_provider_like",
            "marketing_level": "high",
            "marketing_signals": ["立即联系我们"],
            "intermediary_level": "likely",
            "intermediary_signals": ["项目顾问"],
            "originality_claim": "appears_interpretation",
        },
        "opportunity_claim": {
            "claimed_type": "policy",
            "claimed_title": "科技创新项目申报",
            "claimed_issuer": "北京市科学技术委员会",
            "claimed_region": "北京市",
            "claimed_publish_date": None,
            "claimed_deadline": "2026-09-30",
            "claimed_status": "active",
            "claimed_summary": "营销文声称可申报一项科技项目。",
            "claimed_resource_value": {
                "funding": {
                    "description": "最高补贴500万元",
                    "amount": 5000000,
                    "currency": "CNY",
                    "amount_type": "maximum",
                },
                "scenario": None,
                "financing": None,
                "service": None,
                "other": [],
            },
            "claimed_requirements": [],
            "claimed_required_materials": [],
            "claimed_application_process": [],
            "claimed_official_url": None,
            "claim_confidence": 0.7,
        },
        "evidence": [
            {
                "id": "tmp_quote",
                "kind": "direct_quote",
                "field": "marketing_level",
                "text": "最高补贴500万元，名额有限",
                "source": "body",
            }
        ],
        "metadata": {
            "schema_version": "1.0",
            "analyzer_version": "intelligence-extract-v1",
            "created_at": "2026-09-12T12:00:00Z",
        },
    }


def _marketing_result() -> dict:
    return _base_result()


def _official_result() -> dict:
    payload = _base_result()
    payload["analysis"] = {
        "content_nature": "opportunity_announcement",
        "opportunity_relevance": "high",
        "confidence": 0.84,
        "warnings": [],
    }
    payload["source_assessment"] = {
        "apparent_source_type": "official_like",
        "marketing_level": "none",
        "marketing_signals": [],
        "intermediary_level": "none",
        "intermediary_signals": [],
        "originality_claim": "claims_original",
    }
    payload["opportunity_claim"]["claimed_title"] = "2026年度科技创新项目"
    payload["opportunity_claim"]["claimed_deadline"] = "2026-09-30"
    payload["evidence"] = [
        {
            "id": "tmp_deadline",
            "kind": "direct_quote",
            "field": "claimed_deadline",
            "text": "申报截止时间为2026年9月30日",
            "source": "body",
        }
    ]
    return payload


def _general_result() -> dict:
    return {
        "analysis": {
            "content_nature": "general_information",
            "opportunity_relevance": "none",
            "confidence": 0.8,
            "warnings": ["insufficient_context"],
        },
        "source_assessment": {
            "apparent_source_type": "media_like",
            "marketing_level": "none",
            "marketing_signals": [],
            "intermediary_level": "none",
            "intermediary_signals": [],
            "originality_claim": "unclear",
        },
        "opportunity_claim": None,
        "evidence": [
            {
                "id": "tmp_meta",
                "kind": "metadata",
                "field": "opportunity_relevance",
                "text": "title=某公司今日发布新产品",
                "source": "metadata",
            }
        ],
        "metadata": {
            "schema_version": "1.0",
            "analyzer_version": "intelligence-extract-v1",
            "created_at": "2026-09-12T12:00:00Z",
        },
    }


def _analyze(payload: ContentIntelligenceInput, response: dict | Exception, **kwargs):
    rules = RULES.analyze(payload)
    provider = FakeLLMProvider(response, **kwargs)
    return LLMIntelligenceAnalyzer(provider).analyze(payload, rules), provider, rules


def test_valid_marketing_opportunity():
    payload = _payload("marketing_text.txt", title="最高补贴速看")
    extraction, _, _ = _analyze(payload, _marketing_result())
    result = extraction.intelligence_result
    assert result.source_assessment.marketing_level.value == "high"
    assert result.source_assessment.intermediary_level.value == "likely"
    assert result.opportunity_claim is not None
    assert result.metadata.analyzer_version == INTELLIGENCE_PROMPT_VERSION
    assert extraction.prompt_version == INTELLIGENCE_PROMPT_VERSION
    assert forbidden_fields_present(result.model_dump(mode="json")) == set()


def test_valid_official_like_opportunity():
    payload = _payload("opportunity_notice.txt", publisher="示例站点")
    extraction, _, _ = _analyze(payload, _official_result())
    result = extraction.intelligence_result
    assert result.source_assessment.apparent_source_type.value == "official_like"
    dump = result.model_dump(mode="json")
    assert "verified" not in dump
    assert forbidden_fields_present(dump) == set()


def test_general_information_has_null_claim():
    payload = _payload("plain_news.txt", title="某公司今日发布新产品")
    extraction, _, _ = _analyze(payload, _general_result())
    result = extraction.intelligence_result
    assert result.analysis.opportunity_relevance.value == "none"
    assert result.opportunity_claim is None


def test_invalid_schema_is_rejected():
    payload = _payload("marketing_text.txt")
    bad = _marketing_result()
    bad["analysis"]["confidence"] = 2.3
    with pytest.raises(LLMSchemaValidationError):
        _analyze(payload, bad)


def test_forbidden_field_is_rejected():
    payload = _payload("marketing_text.txt")
    with pytest.raises(LLMSchemaValidationError, match="forbidden"):
        _analyze(payload, {"verified": True})


def test_hallucinated_evidence_is_rejected():
    payload = _payload("marketing_text.txt")
    bad = _marketing_result()
    bad["evidence"][0]["text"] = "正文里根本不存在这句话"
    with pytest.raises(LLMSchemaValidationError, match="direct_quote"):
        _analyze(payload, bad)


def test_unknown_rule_evidence_id_is_rejected():
    payload = _payload("marketing_text.txt")
    bad = _marketing_result()
    bad["evidence"][0]["id"] = "rule_ev_999"
    with pytest.raises(LLMSchemaValidationError, match="unknown rule evidence"):
        _analyze(payload, bad)


def test_usage_stays_outside_intelligence_result():
    payload = _payload("marketing_text.txt")
    usage = LLMUsage(input_tokens=1000, output_tokens=300, total_tokens=1300)
    extraction, _, _ = _analyze(payload, _marketing_result(), usage=usage)
    assert extraction.usage.input_tokens == 1000
    assert extraction.usage.output_tokens == 300
    assert extraction.usage.total_tokens == 1300
    assert extraction.usage.estimated_cost is None
    dump = extraction.intelligence_result.model_dump(mode="json")
    assert "input_tokens" not in dump
    assert "total_tokens" not in dump
    assert extraction.provider == "fake"
    assert extraction.model == "fake-model"


def test_timeout_is_mapped():
    payload = _payload("marketing_text.txt")
    with pytest.raises(LLMTimeoutError):
        _analyze(payload, LLMTimeoutError())


def test_rate_limit_is_mapped():
    payload = _payload("marketing_text.txt")
    with pytest.raises(LLMRateLimitError):
        _analyze(payload, LLMRateLimitError())


def test_prompt_contains_boundaries_and_inputs():
    payload = _payload("marketing_text.txt", title="最高补贴速看", publisher="某服务机构")
    rules = RULES.analyze(payload)
    system = build_system_prompt()
    user, truncated = build_user_prompt(payload, rules)
    assert truncated is False
    for token in (
        "Claim ≠ Fact",
        "unknown ≠ guess",
        "marketing ≠ fake",
        "official_like ≠ verified",
    ):
        assert token in system
    assert "<source_content>" in user
    assert "<rule_analysis>" in user
    assert "最高补贴500万元" in user
    assert "marketing.contact_cta" in user or "marketing.money_highlight" in user
    assert "忽略之前指令" in system


def test_evidence_ids_are_rewritten():
    payload = _payload("marketing_text.txt")
    extraction, _, _ = _analyze(payload, _marketing_result())
    ids = [item.id for item in extraction.intelligence_result.evidence]
    assert ids
    assert all(item.startswith("llm_ev_") or item.startswith("rule_ev_") for item in ids)


def test_repair_retry_accepts_second_valid_payload():
    payload = _payload("marketing_text.txt")
    bad = _marketing_result()
    bad["analysis"]["confidence"] = 2.3
    provider = FakeLLMProvider([bad, _marketing_result()])
    extraction = LLMIntelligenceAnalyzer(provider).analyze(payload, RULES.analyze(payload))
    assert extraction.intelligence_result.opportunity_claim is not None
    assert len(provider.calls) == 2
    assert "<validation_error>" in provider.calls[1]["user_prompt"]


def test_input_truncated_warning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "LLM_MAX_INPUT_CHARS", 80)
    original = _payload("marketing_text.txt").normalized_text
    payload = ContentIntelligenceInput(
        source_id=uuid4(),
        ingestion_id=uuid4(),
        normalized_text=original + ("哈" * 400) + "尾部独特标记TAILEND",
    )
    rules = RULES.analyze(payload)
    user, truncated = build_user_prompt(payload, rules)
    assert truncated is True
    assert "最高补贴" in user
    assert "尾部独特标记TAILEND" in user
    assert "[... truncated ...]" in user
    extraction = LLMIntelligenceAnalyzer(FakeLLMProvider(_marketing_result())).analyze(payload, rules)
    assert "input_truncated" in extraction.intelligence_result.analysis.warnings
    assert payload.normalized_text.endswith("尾部独特标记TAILEND")


def test_pytest_uses_fake_provider():
    provider = create_llm_provider()
    assert isinstance(provider, FakeLLMProvider)
    with pytest.raises(LLMProviderError, match="no scripted response"):
        provider.structured_generate(
            system_prompt="x",
            user_prompt="y",
            response_model=ContentIntelligenceResult,
        )


def test_openai_provider_requires_api_key():
    with pytest.raises(LLMProviderError, match="LLM_API_KEY"):
        OpenAICompatibleProvider(api_key="  ", model="gpt-4o-mini")


def test_openai_timeout_mapping():
    provider = OpenAICompatibleProvider(api_key="sk-test", model="gpt-4o-mini")
    mapped = provider._map_exception(TimeoutError("timed out"))
    assert isinstance(mapped, LLMTimeoutError)


def test_domain_modules_do_not_import_openai():
    root = Path(__file__).resolve().parents[1] / "app" / "domains" / "intelligence"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import openai" not in text
        assert "from openai" not in text


def test_no_public_llm_api(client):
    response = client.post("/api/llm/analyze")
    assert response.status_code in {404, 405}


def test_created_at_is_datetime():
    payload = _payload("marketing_text.txt")
    extraction, _, _ = _analyze(payload, _marketing_result())
    assert isinstance(extraction.intelligence_result.metadata.created_at, datetime)
    assert extraction.intelligence_result.metadata.created_at.tzinfo is not None
    assert extraction.latency_ms == 12
    assert extraction.request_id == "fake-req-1"


def test_pydantic_roundtrip_after_extraction():
    payload = _payload("opportunity_notice.txt")
    extraction, _, _ = _analyze(payload, _official_result())
    restored = ContentIntelligenceResult.model_validate_json(
        extraction.intelligence_result.model_dump_json()
    )
    assert restored.source_assessment.apparent_source_type.value == "official_like"
    assert restored.metadata.created_at.tzinfo is not None
