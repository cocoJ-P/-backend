import ipaddress
from uuid import UUID
from pathlib import Path

import httpx

from app.core.database import SessionLocal
from app.integrations.content.fetcher import UrlFetcher
from app.integrations.content.repository import get_latest_by_source
from app.integrations.content.schemas import (
    ExtractionStatus,
    FetchStatus,
    IngestRequest,
    InputType,
)
from app.integrations.content.service import ingest

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def _resolver(hostname: str):
    if hostname == "articles.example.com":
        return [ipaddress.ip_address("93.184.216.34")]
    return [ipaddress.ip_address("8.8.8.8")]


def _fetcher_for(status: int, content_type: str, body: bytes) -> UrlFetcher:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"content-type": content_type}, content=body)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return UrlFetcher(client=client, resolver=_resolver)


def test_ingest_text(client):
    response = client.post(
        "/api/content/ingest",
        json={
            "content_type": "text",
            "content": "这是一段测试政策内容。企业注册地应在北京市。",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["normalized_content"]["fetch_status"] == "not_required"
    assert payload["normalized_content"]["extraction_status"] == "not_required"
    assert payload["normalized_content"]["text"]
    assert payload["normalized_content"]["excerpt"]
    assert payload["source"]["opportunity_id"] is None
    assert payload["source"]["source_type"] == "unknown"


def test_ingest_empty_text_rejected(client):
    response = client.post(
        "/api/content/ingest",
        json={"content_type": "text", "content": "   "},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CONTENT_INPUT"


def test_ingestion_creates_unmapped_source(client):
    response = client.post(
        "/api/content/ingest",
        json={"content_type": "text", "content": "未映射来源的测试正文，需要足够长度。"},
    )
    assert response.status_code == 201
    assert response.json()["source"]["opportunity_id"] is None
    assert response.json()["source"]["id"]


def test_full_text_is_persisted_for_future_intelligence(client):
    body = "完整正文必须被后端保存，供后续 Opportunity Intelligence 读取，不要求前端再次提交。"
    response = client.post(
        "/api/content/ingest",
        json={"content_type": "text", "content": body},
    )
    source_id = response.json()["source"]["id"]
    db = SessionLocal()
    try:
        record = get_latest_by_source(db, UUID(source_id))
        assert record is not None
        assert record.normalized_text
        assert "Opportunity Intelligence" in record.normalized_text
    finally:
        db.close()


def test_ingest_html_url_creates_source_and_ingestion():
    html = (FIXTURES / "official_like.html").read_bytes()
    db = SessionLocal()
    try:
        result = ingest(
            db,
            IngestRequest(
                content_type=InputType.URL,
                content="https://articles.example.com/notice",
            ),
            fetcher=_fetcher_for(200, "text/html", html),
        )
        assert result.normalized_content.fetch_status == FetchStatus.SUCCESS
        assert result.normalized_content.http_status == 200
        assert result.normalized_content.content_type == "text/html"
        assert result.normalized_content.text
        assert result.source.opportunity_id is None
        assert result.ingestion.normalized_text
    finally:
        db.close()


def test_pdf_is_unsupported():
    db = SessionLocal()
    try:
        result = ingest(
            db,
            IngestRequest(
                content_type=InputType.URL,
                content="https://articles.example.com/file.pdf",
            ),
            fetcher=_fetcher_for(200, "application/pdf", b"%PDF-1.4 mock"),
        )
        assert result.normalized_content.fetch_status == FetchStatus.UNSUPPORTED_CONTENT_TYPE
        assert result.normalized_content.extraction_status == ExtractionStatus.UNSUPPORTED
        assert result.source.opportunity_id is None
        assert result.ingestion.normalized_text is None
    finally:
        db.close()


def test_insufficient_html_does_not_fabricate_text():
    html = (FIXTURES / "empty_shell.html").read_bytes()
    db = SessionLocal()
    try:
        result = ingest(
            db,
            IngestRequest(
                content_type=InputType.URL,
                content="https://articles.example.com/app",
            ),
            fetcher=_fetcher_for(200, "text/html", html),
        )
        assert result.normalized_content.extraction_status == ExtractionStatus.INSUFFICIENT_CONTENT
        assert not result.normalized_content.text
        assert result.source.opportunity_id is None
        assert result.ingestion.fetch_status == "success"
    finally:
        db.close()


def test_ingest_localhost_rejected(client):
    response = client.post(
        "/api/content/ingest",
        json={"content_type": "url", "content": "http://127.0.0.1:8000/docs"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSAFE_URL"


def test_ingest_private_ipv4_rejected(client):
    response = client.post(
        "/api/content/ingest",
        json={"content_type": "url", "content": "http://192.168.1.1"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSAFE_URL"


def test_ingest_invalid_scheme_rejected(client):
    response = client.post(
        "/api/content/ingest",
        json={"content_type": "url", "content": "file:///C:/Windows/system.ini"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_URL"
