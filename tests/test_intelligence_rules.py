from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from app.domains.intelligence.contracts import (
    EVIDENCE_TEXT_MAX_CHARS,
    collect_keys,
    forbidden_fields_present,
)
from app.domains.intelligence.enums import AmountKind, DateCandidateKind, URLCandidateKind
from app.domains.intelligence.rules import RULE_VERSION, RuleAnalyzer, RuleAnalysisResult
from app.domains.intelligence.schemas import ContentIntelligenceInput, ContentIntelligenceResult

FIXTURES = Path(__file__).parent / "fixtures" / "intelligence" / "rules"
ANALYZER = RuleAnalyzer()

RULE_JUDGMENT_KEYS = {
    "official",
    "marketing_level",
    "intermediary_level",
    "marketing_score",
    "opportunity_score",
    "intermediary_score",
    "content_nature",
    "claimed_resource_value",
}


def _load_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _payload(text: str, **kwargs) -> ContentIntelligenceInput:
    return ContentIntelligenceInput(
        source_id=uuid4(),
        ingestion_id=uuid4(),
        normalized_text=text,
        **kwargs,
    )


def _codes(result: RuleAnalysisResult) -> set[str]:
    return {item.code for item in result.signals}


def _dump(result: RuleAnalysisResult) -> dict:
    return result.model_dump(mode="json")


def test_rule_analyzer_is_deterministic():
    payload = _payload(_load_text("marketing_text.txt"), title="最高补贴速看")
    first = ANALYZER.analyze(payload)
    second = ANALYZER.analyze(payload)
    exclude = {"metadata": {"created_at": True}}
    assert first.model_dump(mode="json", exclude=exclude) == second.model_dump(
        mode="json", exclude=exclude
    )
    assert first.metadata.rule_version == RULE_VERSION
    assert payload.normalized_text == _load_text("marketing_text.txt")


def test_marketing_signals():
    result = ANALYZER.analyze(_payload(_load_text("marketing_text.txt")))
    codes = _codes(result)
    assert "marketing.money_highlight" in codes
    assert "marketing.urgency_language" in codes
    assert "marketing.contact_cta" in codes
    assert "intermediary.consultant_contact" in codes
    assert "marketing_level" not in collect_keys(_dump(result))


def test_intermediary_signals():
    result = ANALYZER.analyze(_payload(_load_text("intermediary_text.txt")))
    assert "intermediary.application_service" in _codes(result)
    keys = collect_keys(_dump(result))
    assert "intermediary_level" not in keys
    assert result.signals[0].strength.value in {"weak", "medium", "strong"}


def test_opportunity_signals():
    result = ANALYZER.analyze(_payload(_load_text("opportunity_notice.txt")))
    codes = _codes(result)
    assert "opportunity.application_language" in codes
    assert "opportunity.deadline_language" in codes
    deadlines = [item for item in result.date_candidates if item.kind == DateCandidateKind.DEADLINE]
    assert any(item.value == date(2026, 9, 30) for item in deadlines)
    assert "official" not in collect_keys(_dump(result))


def test_plain_news_has_few_opportunity_signals():
    result = ANALYZER.analyze(_payload(_load_text("plain_news.txt")))
    opportunity_codes = {code for code in _codes(result) if code.startswith("opportunity.")}
    assert opportunity_codes == set()
    assert result.amount_candidates == []


def test_contact_information_is_not_intermediary_by_itself():
    result = ANALYZER.analyze(_payload(_load_text("contact_examples.txt")))
    codes = _codes(result)
    assert "structure.contact_information_present" in codes
    assert not any(code.startswith("intermediary.") for code in codes)
    assert "intermediary_level" not in collect_keys(_dump(result))


def test_date_candidate_exact_date():
    result = ANALYZER.analyze(_payload(_load_text("date_examples.txt")))
    values = {item.value for item in result.date_candidates if item.value is not None}
    assert date(2026, 9, 30) in values
    raw_texts = {item.raw_text for item in result.date_candidates}
    assert "2026年9月30日" in raw_texts
    assert "2026-09-30" in raw_texts
    assert "2026/09/30" in raw_texts
    exact = [item for item in result.date_candidates if item.value == date(2026, 9, 30)]
    assert all(item.confidence == 1.0 for item in exact)


def test_ambiguous_date_not_guessed():
    result = ANALYZER.analyze(_payload(_load_text("date_examples.txt")))
    fuzzy = [
        item
        for item in result.date_candidates
        if item.raw_text in {"本月底", "近期", "下周", "下周五", "9月底"}
    ]
    assert {item.raw_text for item in fuzzy} >= {"本月底", "近期", "下周"}
    assert all(item.value is None for item in fuzzy)
    assert all(item.confidence == 0.0 for item in fuzzy)


def test_amount_candidates():
    result = ANALYZER.analyze(_payload(_load_text("amount_examples.txt")))
    amounts = [item.amount for item in result.amount_candidates]
    assert 1_000_000.0 in amounts
    assert 500_000.0 in amounts
    assert 300_000.0 in amounts
    assert 5_000_000.0 in amounts
    assert all(item.currency == "CNY" for item in result.amount_candidates)
    assert all(item.unit == "元" for item in result.amount_candidates)


def test_multiple_amounts_not_collapsed():
    result = ANALYZER.analyze(_payload(_load_text("amount_examples.txt")))
    assert len(result.amount_candidates) >= 4
    kinds = {item.kind for item in result.amount_candidates}
    assert AmountKind.AWARD in kinds
    assert AmountKind.UNKNOWN in kinds
    keys = collect_keys(_dump(result))
    assert "claimed_resource_value" not in keys
    assert "funding" not in keys


def test_url_candidate():
    result = ANALYZER.analyze(_payload(_load_text("url_examples.txt")))
    assert result.url_candidates
    candidate = result.url_candidates[0]
    assert candidate.url == "https://example.gov.cn/policy/123"
    assert candidate.kind == URLCandidateKind.OFFICIAL_DOMAIN_LIKE


def test_gov_domain_is_only_official_like():
    result = ANALYZER.analyze(_payload(_load_text("url_examples.txt")))
    dump = _dump(result)
    keys = collect_keys(dump)
    assert forbidden_fields_present(dump) == set()
    assert "verified_official_url" not in keys
    assert "official" not in keys
    assert "is_official" not in keys
    assert all(item.kind == URLCandidateKind.OFFICIAL_DOMAIN_LIKE for item in result.url_candidates)


def test_signal_evidence_integrity():
    result = ANALYZER.analyze(_payload(_load_text("marketing_text.txt")))
    known = {item.id for item in result.evidence}
    for signal in result.signals:
        assert signal.evidence_ids
        assert all(evidence_id in known for evidence_id in signal.evidence_ids)
    for candidate in (
        *result.date_candidates,
        *result.url_candidates,
        *result.amount_candidates,
        *result.entity_candidates,
    ):
        assert candidate.evidence_id in known
    assert all(len(item.text) <= EVIDENCE_TEXT_MAX_CHARS for item in result.evidence)
    assert all(item.id.startswith("rule_ev_") for item in result.evidence)


def test_duplicate_signals_are_merged():
    text = "请联系我们。" * 10
    result = ANALYZER.analyze(_payload(text))
    cta = [item for item in result.signals if item.code == "marketing.contact_cta"]
    assert len(cta) == 1
    assert cta[0].occurrence_count == 10
    assert 1 <= len(cta[0].evidence_ids) <= 5


def test_rule_analysis_json_serialization():
    result = ANALYZER.analyze(
        _payload(
            _load_text("opportunity_notice.txt"),
            publisher="示例发布方",
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    )
    restored = RuleAnalysisResult.model_validate_json(result.model_dump_json())
    assert restored.metadata.rule_version == RULE_VERSION
    assert "metadata.publisher_present" in _codes(restored)
    assert "metadata.published_at_present" in _codes(restored)
    assert not isinstance(result, ContentIntelligenceResult)
    assert RULE_JUDGMENT_KEYS.isdisjoint(collect_keys(_dump(result)))


def test_no_public_rule_api(client):
    response = client.post("/api/rules/analyze")
    assert response.status_code in {404, 405, 422}
