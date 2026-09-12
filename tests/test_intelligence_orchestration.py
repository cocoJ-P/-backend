from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.domains.intelligence.enums import IntelligenceRunStatus
from app.domains.intelligence.fingerprint import (
    compute_analysis_fingerprint,
    compute_input_hash,
)
from app.domains.intelligence.llm.prompts import INTELLIGENCE_PROMPT_VERSION
from app.domains.intelligence.models import IntelligenceRun
from app.domains.intelligence.orchestration import (
    OpportunityIntelligenceOrchestrator,
    load_intelligence_result,
    load_rule_result,
)
from app.domains.intelligence.rules.schemas import RULE_VERSION, RuleAnalysisResult
from app.domains.intelligence.schemas import ContentIntelligenceResult
from app.domains.opportunity.models import OpportunitySource
from app.integrations.content.models import IngestedContent
from app.integrations.content.repository import add_ingested_content
from app.integrations.llm.errors import LLMTimeoutError
from app.integrations.llm.providers.fake import FakeLLMProvider

FIXTURES = Path(__file__).parent / "fixtures" / "intelligence" / "rules"
NOTICE = (FIXTURES / "opportunity_notice.txt").read_text(encoding="utf-8")
NEWS = (FIXTURES / "plain_news.txt").read_text(encoding="utf-8")
MARKETING = (FIXTURES / "marketing_text.txt").read_text(encoding="utf-8")


def _ingest(client, text: str) -> dict:
    response = client.post(
        "/api/content/ingest",
        json={"content_type": "text", "content": text},
    )
    assert response.status_code == 201
    payload = response.json()
    payload["source"]["id"] = UUID(payload["source"]["id"])
    payload["ingestion"]["id"] = UUID(payload["ingestion"]["id"])
    return payload


def _quote(text: str) -> str:
    line = text.strip().splitlines()[0].strip()
    return line[:80]


def _success_payload(text: str, *, claim: bool = True, official: bool = True) -> dict:
    evidence_text = "申报截止时间为2026年9月30日" if "申报截止时间为2026年9月30日" in text else _quote(text)
    payload = {
        "analysis": {
            "content_nature": "opportunity_announcement" if claim else "general_information",
            "opportunity_relevance": "high" if claim else "none",
            "confidence": 0.8,
            "warnings": [],
        },
        "source_assessment": {
            "apparent_source_type": "official_like" if official else "media_like",
            "marketing_level": "none",
            "marketing_signals": [],
            "intermediary_level": "none",
            "intermediary_signals": [],
            "originality_claim": "claims_original" if claim else "unclear",
        },
        "opportunity_claim": None,
        "evidence": [
            {
                "id": "tmp_1",
                "kind": "direct_quote",
                "field": "claimed_deadline" if claim else "content_nature",
                "text": evidence_text,
                "source": "body",
            }
        ],
        "metadata": {
            "schema_version": "1.0",
            "analyzer_version": "intelligence-extract-v1",
            "created_at": "2026-09-12T12:00:00Z",
        },
    }
    if claim:
        payload["opportunity_claim"] = {
            "claimed_type": "policy",
            "claimed_title": "2026年度科技创新项目",
            "claimed_issuer": "示例主管部门",
            "claimed_region": "北京市",
            "claimed_publish_date": None,
            "claimed_deadline": "2026-09-30",
            "claimed_status": "active",
            "claimed_summary": "内容声称组织开展科技创新项目申报。",
            "claimed_resource_value": None,
            "claimed_requirements": [],
            "claimed_required_materials": [],
            "claimed_application_process": [],
            "claimed_official_url": None,
            "claim_confidence": 0.8,
        }
    return payload


def _run_count(db) -> int:
    return int(db.scalar(select(func.count()).select_from(IntelligenceRun)) or 0)


def _analyze(db, source_id, fake, **kwargs):
    return OpportunityIntelligenceOrchestrator(db, provider=fake).analyze_source(
        source_id, **kwargs
    )


def test_pipeline_persists_succeeded_run(client):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    fake = FakeLLMProvider(_success_payload(NOTICE))
    db = SessionLocal()
    try:
        execution = _analyze(db, source_id, fake)
        assert execution.reused is False
        assert execution.run.status == IntelligenceRunStatus.SUCCEEDED
        assert execution.intelligence_result is not None
        assert execution.intelligence_result.opportunity_claim is not None
        assert execution.run.rule_version == RULE_VERSION
        assert execution.run.prompt_version == INTELLIGENCE_PROMPT_VERSION
        assert execution.run.provider == "fake"
        assert _run_count(db) == 1
        run = db.get(IntelligenceRun, execution.run.id)
        assert run is not None
        load_intelligence_result(run)
        load_rule_result(run)
        assert ingested["source"]["opportunity_id"] is None
        source = db.get(OpportunitySource, source_id)
        assert source is not None
        assert source.opportunity_id is None
        assert source.source_type == "unknown"
    finally:
        db.close()


def test_latest_analyzable_ingestion_skips_failed(client):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    success_ingestion_id = ingested["ingestion"]["id"]
    db = SessionLocal()
    try:
        failed = IngestedContent(
            source_id=source_id,
            input_type="url",
            fetch_status="failed",
            extraction_status="failed",
            normalized_text=None,
        )
        add_ingested_content(db, failed)
        db.commit()
        fake = FakeLLMProvider(_success_payload(NOTICE))
        execution = _analyze(db, source_id, fake)
        assert execution.run.ingestion_id == success_ingestion_id
    finally:
        db.close()


def test_explicit_ingestion_id_and_mismatch(client):
    first = _ingest(client, NOTICE)
    second = _ingest(client, MARKETING)
    db = SessionLocal()
    try:
        fake = FakeLLMProvider(_success_payload(NOTICE))
        execution = _analyze(
            db,
            first["source"]["id"],
            fake,
            ingestion_id=first["ingestion"]["id"],
        )
        assert execution.run.ingestion_id == first["ingestion"]["id"]
        with pytest.raises(AppException) as exc_info:
            _analyze(
                db,
                first["source"]["id"],
                FakeLLMProvider(_success_payload(NOTICE)),
                ingestion_id=second["ingestion"]["id"],
            )
        assert exc_info.value.code == "INGESTION_SOURCE_MISMATCH"
        assert exc_info.value.status_code == 409
    finally:
        db.close()


def test_cache_reuse_does_not_call_llm_again(client):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    fake = FakeLLMProvider(_success_payload(NOTICE))
    db = SessionLocal()
    try:
        first = _analyze(db, source_id, fake)
        second = _analyze(db, source_id, fake, force=False)
        assert second.reused is True
        assert second.run.id == first.run.id
        assert len(fake.calls) == 1
        assert _run_count(db) == 1
    finally:
        db.close()


def test_force_creates_new_run(client):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    fake = FakeLLMProvider(_success_payload(NOTICE))
    db = SessionLocal()
    try:
        first = _analyze(db, source_id, fake)
        second = _analyze(db, source_id, fake, force=True)
        assert second.reused is False
        assert second.run.id != first.run.id
        assert len(fake.calls) == 2
        assert _run_count(db) == 2
    finally:
        db.close()


def test_changed_ingestion_does_not_reuse(client):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    db = SessionLocal()
    try:
        fake = FakeLLMProvider(_success_payload(NOTICE))
        first = _analyze(db, source_id, fake)
        changed = IngestedContent(
            source_id=source_id,
            input_type="text",
            fetch_status="not_required",
            extraction_status="not_required",
            normalized_text=NEWS,
        )
        add_ingested_content(db, changed)
        db.commit()
        fake_news = FakeLLMProvider(_success_payload(NEWS, claim=False, official=False))
        second = _analyze(db, source_id, fake_news)
        assert second.reused is False
        assert second.run.id != first.run.id
        assert second.run.input_hash != first.run.input_hash
        assert second.run.analysis_fingerprint != first.run.analysis_fingerprint
    finally:
        db.close()


def test_fingerprint_changes_with_prompt_or_model():
    input_hash = compute_input_hash(
        title="t",
        publisher="p",
        source_url="https://example.com",
        published_at=None,
        normalized_text="正文",
    )
    base = dict(
        input_hash=input_hash,
        rule_version="rules-v1",
        prompt_version="intelligence-extract-v1",
        provider="openai",
        model="gpt-4o-mini",
    )
    original = compute_analysis_fingerprint(**base)
    assert compute_analysis_fingerprint(**{**base, "prompt_version": "v2"}) != original
    assert compute_analysis_fingerprint(**{**base, "model": "other-model"}) != original
    changed_input = compute_input_hash(
        title="t",
        publisher="p",
        source_url="https://example.com",
        published_at=None,
        normalized_text="另一段正文",
    )
    assert changed_input != input_hash


def test_timeout_persists_failed_run(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-secret-key")
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    fake = FakeLLMProvider(LLMTimeoutError("timed out sk-secret-key"))
    db = SessionLocal()
    try:
        with pytest.raises(AppException) as exc_info:
            _analyze(db, source_id, fake)
        assert exc_info.value.code == "LLM_TIMEOUT"
        assert exc_info.value.status_code == 504
        assert exc_info.value.details["run_id"]
        run = db.scalars(select(IntelligenceRun)).first()
        assert run is not None
        assert run.status == IntelligenceRunStatus.FAILED.value
        assert run.error_code == "LLM_TIMEOUT"
        assert run.completed_at is not None
        assert "sk-secret-key" not in (run.error_message or "")
    finally:
        db.close()


def test_schema_failure_persists_failed_run(client):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    bad = _success_payload(NOTICE)
    bad["analysis"]["confidence"] = 2.3
    fake = FakeLLMProvider(bad)
    db = SessionLocal()
    try:
        with pytest.raises(AppException) as exc_info:
            _analyze(db, source_id, fake)
        assert exc_info.value.code == "LLM_SCHEMA_VALIDATION_ERROR"
        run = db.scalars(select(IntelligenceRun)).first()
        assert run is not None
        assert run.status == IntelligenceRunStatus.FAILED.value
        assert run.error_code == "LLM_SCHEMA_VALIDATION_ERROR"
        assert run.completed_at is not None
    finally:
        db.close()


def test_no_opportunity_is_still_succeeded(client):
    ingested = _ingest(client, NEWS)
    source_id = ingested["source"]["id"]
    fake = FakeLLMProvider(_success_payload(NEWS, claim=False, official=False))
    db = SessionLocal()
    try:
        execution = _analyze(db, source_id, fake)
        assert execution.run.status == IntelligenceRunStatus.SUCCEEDED
        assert execution.intelligence_result is not None
        assert execution.intelligence_result.analysis.opportunity_relevance.value == "none"
        assert execution.intelligence_result.opportunity_claim is None
    finally:
        db.close()


def test_partial_extraction_adds_warning(client):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    db = SessionLocal()
    try:
        record = db.get(IngestedContent, ingested["ingestion"]["id"])
        assert record is not None
        record.extraction_status = "partial"
        db.commit()
        fake = FakeLLMProvider(_success_payload(NOTICE))
        execution = _analyze(db, source_id, fake)
        assert "source_extraction_partial" in execution.intelligence_result.analysis.warnings
    finally:
        db.close()


def test_json_snapshot_roundtrip(client):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    fake = FakeLLMProvider(_success_payload(NOTICE))
    db = SessionLocal()
    try:
        execution = _analyze(db, source_id, fake)
        run = db.get(IntelligenceRun, execution.run.id)
        assert run is not None
        restored_intel = ContentIntelligenceResult.model_validate(run.intelligence_result_json)
        restored_rules = RuleAnalysisResult.model_validate(run.rule_result_json)
        assert restored_intel.analysis.content_nature.value == "opportunity_announcement"
        assert restored_rules.metadata.rule_version == RULE_VERSION
        assert run.usage_json["input_tokens"] == 1000
        assert "latency_ms" in run.usage_json
    finally:
        db.close()


def test_run_history_is_newest_first(client):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    fake = FakeLLMProvider(_success_payload(NOTICE))
    db = SessionLocal()
    try:
        a = _analyze(db, source_id, fake, force=True)
        b = _analyze(db, source_id, fake, force=True)
        c = _analyze(db, source_id, fake, force=True)
        ids = [str(a.run.id), str(b.run.id), str(c.run.id)]
        response = client.get(f"/api/opportunity-sources/{source_id}/intelligence-runs")
        assert response.status_code == 200
        returned = [item["id"] for item in response.json()]
        assert returned == list(reversed(ids))
    finally:
        db.close()


def test_analyze_api_success_reuse_and_force(client, monkeypatch):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    fake = FakeLLMProvider(_success_payload(NOTICE))
    monkeypatch.setattr(
        "app.domains.intelligence.orchestration.create_llm_provider",
        lambda: fake,
    )
    first = client.post(f"/api/opportunity-sources/{source_id}/analyze", json={})
    assert first.status_code == 200
    body = first.json()
    assert body["reused"] is False
    assert body["run"]["status"] == "succeeded"
    assert body["intelligence_result"]["analysis"]
    assert body["intelligence_result"]["source_assessment"]
    assert body["run"]["rule_version"]
    assert body["run"]["prompt_version"]
    assert body["run"]["provider"]
    assert body["run"]["model"]

    second = client.post(
        f"/api/opportunity-sources/{source_id}/analyze",
        json={"force": False},
    )
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["run"]["id"] == body["run"]["id"]
    assert len(fake.calls) == 1

    third = client.post(
        f"/api/opportunity-sources/{source_id}/analyze",
        json={"force": True},
    )
    assert third.status_code == 200
    assert third.json()["reused"] is False
    assert third.json()["run"]["id"] != body["run"]["id"]
    assert len(fake.calls) == 2

    detail = client.get(f"/api/intelligence-runs/{body['run']['id']}")
    assert detail.status_code == 200
    assert detail.json()["intelligence_result"]["analysis"]["content_nature"]


def test_analyze_missing_source(client):
    response = client.post(f"/api/opportunity-sources/{uuid4()}/analyze", json={})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OPPORTUNITY_SOURCE_NOT_FOUND"


def test_content_not_analyzable(client):
    db = SessionLocal()
    try:
        source = OpportunitySource(source_type="unknown", title="不可分析")
        db.add(source)
        db.flush()
        add_ingested_content(
            db,
            IngestedContent(
                source_id=source.id,
                input_type="url",
                fetch_status="success",
                extraction_status="unsupported",
                normalized_text=None,
            ),
        )
        db.commit()
        source_id = source.id
    finally:
        db.close()
    response = client.post(f"/api/opportunity-sources/{source_id}/analyze", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTENT_NOT_ANALYZABLE"


def test_llm_not_configured_returns_503(client, monkeypatch):
    ingested = _ingest(client, NOTICE)
    source_id = ingested["source"]["id"]
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    response = client.post(f"/api/opportunity-sources/{source_id}/analyze", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
    health = client.get("/api/health")
    assert health.status_code == 200


def test_missing_run_not_found(client):
    response = client.get(f"/api/intelligence-runs/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INTELLIGENCE_RUN_NOT_FOUND"
