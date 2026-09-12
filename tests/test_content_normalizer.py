from app.core.exceptions import AppException
from app.integrations.content.normalizer import normalize_text
from app.integrations.content.schemas import ExtractionStatus, FetchStatus, InputType


def test_text_normalizes_successfully():
    result = normalize_text("这是一段测试政策内容。企业注册地应在北京市。")
    assert result.input_type == InputType.TEXT
    assert result.fetch_status == FetchStatus.NOT_REQUIRED
    assert result.extraction_status == ExtractionStatus.NOT_REQUIRED
    assert "北京市" in (result.text or "")
    assert result.title is None


def test_empty_text_rejected():
    try:
        normalize_text("   ")
        raise AssertionError("expected empty text to fail")
    except AppException as exc:
        assert exc.code == "INVALID_CONTENT_INPUT"
        assert exc.status_code == 400


def test_whitespace_normalized():
    result = normalize_text("第一段。\r\n\r\n\r\n   第二段。   ")
    assert result.text == "第一段。\n\n第二段。"


def test_unicode_text_preserved():
    result = normalize_text("Cafe\u0301 test")
    assert "Cafe" in (result.text or "") or "Café" in (result.text or "")


def test_chinese_text_preserved():
    result = normalize_text("北京市科学技术委员会发布申报通知。")
    assert "科学技术委员会" in (result.text or "")


def test_excerpt_generated():
    payload = "企业" * 300
    result = normalize_text(payload)
    assert result.excerpt is not None
    assert len(result.excerpt) <= 400
