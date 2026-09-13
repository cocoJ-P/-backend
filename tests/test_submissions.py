from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.core.time import utc_now
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
from app.domains.intelligence.models import IntelligenceRun
from app.domains.opportunity.models import Opportunity
from app.domains.submission.enums import SubmissionFailureStage, SubmissionStatus
from app.domains.submission.models import UserSubmission
from app.integrations.content.service import ingest
from app.integrations.llm.errors import LLMSchemaValidationError
from app.integrations.llm.providers.fake import FakeLLMProvider

FIXTURES = Path(__file__).parent / "fixtures" / "intelligence" / "rules"
NOTICE = (FIXTURES / "opportunity_notice.txt").read_text(encoding="utf-8")


def _header(user_id=DEMO_USER_ID) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user_id)}


def _seed_identity() -> None:
    db = SessionLocal()
    try:
        seed_demo_identity(db)
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


def _create(client, content: str = "某申报通知...", input_type: str = "text"):
    _seed_identity()
    response = client.post(
        "/api/user-submissions",
        headers=_header(),
        json={"input_type": input_type, "content": content},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _quote(text: str) -> str:
    line = text.strip().splitlines()[0].strip()
    return line[:80]


def _success_payload(text: str) -> dict:
    evidence_text = "申报截止时间为2026年9月30日" if "申报截止时间为2026年9月30日" in text else _quote(text)
    return {
        "analysis": {
            "content_nature": "opportunity_announcement",
            "opportunity_relevance": "high",
            "confidence": 0.8,
            "warnings": [],
        },
        "source_assessment": {
            "apparent_source_type": "official_like",
            "marketing_level": "none",
            "marketing_signals": [],
            "intermediary_level": "none",
            "intermediary_signals": [],
            "originality_claim": "claims_original",
        },
        "opportunity_claim": {
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
        },
        "evidence": [
            {
                "id": "tmp_1",
                "kind": "direct_quote",
                "field": "claimed_deadline",
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


def _use_fake_llm(monkeypatch, provider: FakeLLMProvider) -> None:
    monkeypatch.setattr(
        "app.domains.intelligence.orchestration.create_llm_provider",
        lambda: provider,
    )


def _count(model) -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.count()).select_from(model)) or 0)
    finally:
        db.close()


def _get_submission(submission_id: str) -> UserSubmission:
    db = SessionLocal()
    try:
        row = db.get(UserSubmission, UUID(submission_id))
        assert row is not None
        db.expunge(row)
        return row
    finally:
        db.close()


def test_create_submission_uses_current_identity(client):
    payload = _create(client)
    assert payload["status"] == "pending"
    assert payload["input_type"] == "text"
    assert payload["input_preview"] == "某申报通知..."
    assert payload["user"]["id"] == str(DEMO_USER_ID)
    assert payload["user"]["display_name"] == "Demo User"
    assert payload["enterprise"]["id"] == str(DEMO_ENTERPRISE_ID)
    assert payload["enterprise"]["name"] == "筑脉科技"
    assert "input_content" not in payload

    stored = _get_submission(payload["id"])
    assert stored.user_id == DEMO_USER_ID
    assert stored.enterprise_id == DEMO_ENTERPRISE_ID
    assert stored.status == SubmissionStatus.PENDING.value
    assert stored.input_content == "某申报通知..."
    assert stored.source_id is None
    assert stored.ingestion_id is None
    assert stored.intelligence_run_id is None


def test_create_rejects_spoofed_identity_fields(client):
    _seed_identity()
    response = client.post(
        "/api/user-submissions",
        headers=_header(),
        json={
            "user_id": str(uuid4()),
            "enterprise_id": str(uuid4()),
            "input_type": "text",
            "content": "某申报通知...",
        },
    )
    assert response.status_code == 422


def test_submission_api_requires_identity(client):
    response = client.post(
        "/api/user-submissions",
        json={"input_type": "text", "content": "某申报通知..."},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "DEV_IDENTITY_REQUIRED"


def test_create_rejects_empty_and_invalid_url(client):
    _seed_identity()
    empty = client.post(
        "/api/user-submissions",
        headers=_header(),
        json={"input_type": "text", "content": "   "},
    )
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "INVALID_SUBMISSION_INPUT"

    invalid_url = client.post(
        "/api/user-submissions",
        headers=_header(),
        json={"input_type": "url", "content": "ftp://example.com/article"},
    )
    assert invalid_url.status_code == 400
    assert invalid_url.json()["error"]["code"] == "INVALID_SUBMISSION_INPUT"


def test_process_text_success_binds_technical_ids(client, monkeypatch):
    created = _create(client, NOTICE)
    fake = FakeLLMProvider(_success_payload(NOTICE))
    _use_fake_llm(monkeypatch, fake)

    response = client.post(
        f"/api/user-submissions/{created['id']}/process",
        headers=_header(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    submission = body["submission"]
    assert submission["status"] == "succeeded"
    assert submission["source_id"]
    assert submission["ingestion_id"]
    assert submission["intelligence_run_id"]
    assert submission["input_content"] == NOTICE.strip()
    assert body["submitted_by"]["id"] == str(DEMO_USER_ID)
    assert body["enterprise"]["name"] == "筑脉科技"
    assert body["content"]["excerpt"]
    assert "normalized_text" not in body["content"]
    assert body["intelligence"]["status"] == "succeeded"
    assert body["intelligence"]["result"]["opportunity_claim"]["claimed_title"] == "2026年度科技创新项目"
    assert submission["failure_stage"] is None
    assert submission["error_code"] is None
    assert submission["completed_at"]

    stored = _get_submission(created["id"])
    assert stored.status == SubmissionStatus.SUCCEEDED.value
    assert stored.source_id is not None
    assert stored.ingestion_id is not None
    assert stored.intelligence_run_id is not None


def test_process_ingest_failure_persists_original_error(client, monkeypatch):
    created = _create(client)

    def fail_ingest(*_args, **_kwargs):
        raise AppException("FETCH_FAILED", "Could not fetch URL", status_code=502)

    monkeypatch.setattr("app.domains.submission.orchestration.ingest", fail_ingest)
    response = client.post(
        f"/api/user-submissions/{created['id']}/process",
        headers=_header(),
    )
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "FETCH_FAILED"
    assert error["details"]["submission_id"] == created["id"]
    assert error["details"]["failure_stage"] == "ingest"

    stored = _get_submission(created["id"])
    assert stored.status == SubmissionStatus.FAILED.value
    assert stored.failure_stage == SubmissionFailureStage.INGEST.value
    assert stored.error_code == "FETCH_FAILED"
    assert stored.source_id is None
    assert stored.ingestion_id is None
    assert stored.completed_at is not None


def test_retry_after_ingest_failure_reingests_and_succeeds(client, monkeypatch):
    created = _create(client, NOTICE)
    calls = {"ingest": 0}
    real_ingest = ingest

    def flaky_ingest(*args, **kwargs):
        calls["ingest"] += 1
        if calls["ingest"] == 1:
            raise AppException("FETCH_FAILED", "Could not fetch URL", status_code=502)
        return real_ingest(*args, **kwargs)

    monkeypatch.setattr("app.domains.submission.orchestration.ingest", flaky_ingest)
    _use_fake_llm(monkeypatch, FakeLLMProvider(_success_payload(NOTICE)))

    first = client.post(f"/api/user-submissions/{created['id']}/process", headers=_header())
    assert first.status_code == 502
    assert _get_submission(created["id"]).failure_stage == "ingest"

    second = client.post(f"/api/user-submissions/{created['id']}/process", headers=_header())
    assert second.status_code == 200, second.text
    assert second.json()["submission"]["status"] == "succeeded"
    assert calls["ingest"] == 2


def test_process_analyze_failure_keeps_ingestion(client, monkeypatch):
    created = _create(client, NOTICE)
    ingest_calls = {"n": 0}
    real_ingest = ingest

    def counting_ingest(*args, **kwargs):
        ingest_calls["n"] += 1
        return real_ingest(*args, **kwargs)

    monkeypatch.setattr("app.domains.submission.orchestration.ingest", counting_ingest)
    _use_fake_llm(monkeypatch, FakeLLMProvider(LLMSchemaValidationError("bad schema")))

    response = client.post(
        f"/api/user-submissions/{created['id']}/process",
        headers=_header(),
    )
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "LLM_SCHEMA_VALIDATION_ERROR"
    assert error["details"]["submission_id"] == created["id"]
    assert error["details"]["failure_stage"] == "analyze"
    assert "run_id" in error["details"]

    stored = _get_submission(created["id"])
    assert stored.status == SubmissionStatus.FAILED.value
    assert stored.failure_stage == SubmissionFailureStage.ANALYZE.value
    assert stored.error_code == "LLM_SCHEMA_VALIDATION_ERROR"
    assert stored.source_id is not None
    assert stored.ingestion_id is not None
    assert ingest_calls["n"] == 1


def test_retry_after_analyze_failure_skips_ingest(client, monkeypatch):
    created = _create(client, NOTICE)
    ingest_calls = {"n": 0}
    real_ingest = ingest

    def counting_ingest(*args, **kwargs):
        ingest_calls["n"] += 1
        return real_ingest(*args, **kwargs)

    monkeypatch.setattr("app.domains.submission.orchestration.ingest", counting_ingest)
    fake = FakeLLMProvider(
        [
            LLMSchemaValidationError("bad schema"),
            LLMSchemaValidationError("bad schema still"),
            _success_payload(NOTICE),
        ]
    )
    _use_fake_llm(monkeypatch, fake)

    first = client.post(f"/api/user-submissions/{created['id']}/process", headers=_header())
    assert first.status_code == 502
    assert ingest_calls["n"] == 1
    failed = _get_submission(created["id"])
    source_id = failed.source_id
    ingestion_id = failed.ingestion_id
    assert source_id is not None
    assert ingestion_id is not None

    second = client.post(f"/api/user-submissions/{created['id']}/process", headers=_header())
    assert second.status_code == 200, second.text
    assert second.json()["submission"]["status"] == "succeeded"
    assert ingest_calls["n"] == 1
    assert UUID(second.json()["submission"]["source_id"]) == source_id
    assert UUID(second.json()["submission"]["ingestion_id"]) == ingestion_id
    assert len(fake.calls) == 3


def test_process_rejects_concurrent_processing(client):
    created = _create(client)
    db = SessionLocal()
    try:
        row = db.get(UserSubmission, UUID(created["id"]))
        assert row is not None
        row.status = SubmissionStatus.ANALYZING.value
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/api/user-submissions/{created['id']}/process",
        headers=_header(),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUBMISSION_ALREADY_PROCESSING"


def test_process_succeeded_is_idempotent(client, monkeypatch):
    created = _create(client, NOTICE)
    fake = FakeLLMProvider(_success_payload(NOTICE))
    _use_fake_llm(monkeypatch, fake)

    first = client.post(f"/api/user-submissions/{created['id']}/process", headers=_header())
    assert first.status_code == 200
    run_id = first.json()["submission"]["intelligence_run_id"]
    runs_after_first = _count(IntelligenceRun)
    assert len(fake.calls) == 1

    second = client.post(f"/api/user-submissions/{created['id']}/process", headers=_header())
    assert second.status_code == 200
    assert second.json()["submission"]["status"] == "succeeded"
    assert second.json()["submission"]["intelligence_run_id"] == run_id
    assert _count(IntelligenceRun) == runs_after_first
    assert len(fake.calls) == 1


def test_process_success_does_not_create_opportunity(client, monkeypatch):
    before = _count(Opportunity)
    created = _create(client, NOTICE)
    _use_fake_llm(monkeypatch, FakeLLMProvider(_success_payload(NOTICE)))
    response = client.post(f"/api/user-submissions/{created['id']}/process", headers=_header())
    assert response.status_code == 200
    assert _count(Opportunity) == before


def test_get_submission_hides_other_enterprise(client):
    created = _create(client)
    other_user_id = _seed_other_identity()

    hidden = client.get(
        f"/api/user-submissions/{created['id']}",
        headers=_header(other_user_id),
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "SUBMISSION_NOT_FOUND"

    missing = client.get(
        f"/api/user-submissions/{uuid4()}",
        headers=_header(),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SUBMISSION_NOT_FOUND"


def test_list_is_enterprise_scoped_newest_first_and_lightweight(client):
    first = _create(client, "第一次提交正文需要足够长度。")
    second = _create(client, "第二次提交正文需要足够长度。")
    third = _create(client, "第三次提交正文需要足够长度。")
    db = SessionLocal()
    try:
        base = utc_now()
        for index, item_id in enumerate((first["id"], second["id"], third["id"])):
            row = db.get(UserSubmission, UUID(item_id))
            assert row is not None
            row.created_at = base + timedelta(seconds=index)
            db.add(row)
        db.commit()
    finally:
        db.close()
    other_user_id = _seed_other_identity()

    own = client.get("/api/user-submissions", headers=_header())
    assert own.status_code == 200
    items = own.json()["items"]
    assert [item["id"] for item in items] == [third["id"], second["id"], first["id"]]
    for item in items:
        assert "input_content" not in item
        assert "intelligence" not in item
        assert "intelligence_result" not in item
        assert item["display_title"] == "正文提交"
        assert item["input_preview"]
        assert item["submitted_by"]["display_name"] == "Demo User"

    isolated = client.get("/api/user-submissions", headers=_header(other_user_id))
    assert isolated.status_code == 200
    assert isolated.json()["items"] == []

    failed_only = client.get("/api/user-submissions?status=failed", headers=_header())
    assert failed_only.status_code == 200
    assert failed_only.json()["items"] == []


def test_existing_content_intelligence_and_me_remain_compatible(client, monkeypatch):
    ingest_response = client.post(
        "/api/content/ingest",
        json={"content_type": "text", "content": NOTICE},
    )
    assert ingest_response.status_code == 201
    source_id = ingest_response.json()["source"]["id"]

    _use_fake_llm(monkeypatch, FakeLLMProvider(_success_payload(NOTICE)))
    analyze_response = client.post(
        f"/api/opportunity-sources/{source_id}/analyze",
        json={},
    )
    assert analyze_response.status_code == 200
    assert analyze_response.json()["run"]["status"] == "succeeded"

    _seed_identity()
    me = client.get("/api/me", headers=_header())
    assert me.status_code == 200
    assert me.json()["user"]["id"] == str(DEMO_USER_ID)


def test_openapi_user_submission_routes_require_dev_identity(client):
    payload = client.get("/openapi.json").json()
    paths = payload["paths"]
    expected = {
        "/api/user-submissions": ["post", "get"],
        "/api/user-submissions/{submission_id}/process": ["post"],
        "/api/user-submissions/{submission_id}": ["get"],
    }
    for path, methods in expected.items():
        assert path in paths
        for method in methods:
            parameters = paths[path][method].get("parameters", [])
            header = next(item for item in parameters if item.get("name") == "X-Dev-User-Id")
            assert header["in"] == "header"
    schemas = payload["components"]["schemas"]
    assert "CreateUserSubmissionRequest" in schemas
    assert "UserSubmissionSummary" in schemas
    assert "UserSubmissionDetail" in schemas
    assert "UserSubmissionListResponse" in schemas
    assert "SubmissionContentSummary" in schemas
    assert "SubmissionIntelligenceSummary" in schemas
    assert schemas["CreateUserSubmissionRequest"].get("additionalProperties") is False
