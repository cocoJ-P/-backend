from pathlib import Path

from app.integrations.content.extractor import HtmlExtractor
from app.integrations.content.schemas import ExtractionStatus

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def _extract(name: str):
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return HtmlExtractor().extract(html, url="https://articles.example.com/page")


def test_html_article_extraction():
    result = _extract("official_like.html")
    assert result.text
    assert "研发创新支持专项" in result.text
    assert "首页" not in (result.text or "") or "企业注册地" in result.text


def test_html_metadata_extraction():
    result = _extract("official_like.html")
    assert result.title == "北京市科技型企业研发创新支持专项"
    assert result.publisher == "北京市科学技术委员会"
    assert result.published_at is not None
    assert result.published_at.tzinfo is not None


def test_missing_metadata_allowed():
    result = _extract("no_metadata.html")
    assert result.publisher is None
    assert result.published_at is None
    assert "publisher_not_found" in result.warnings
    assert "published_at_not_found" in result.warnings
    assert result.text


def test_navigation_noise_reduced():
    result = _extract("navigation_heavy.html")
    assert result.text
    assert "loan interest subsidy" in result.text.lower() or "Loan interest subsidy" in (result.text or "")


def test_date_parsing_from_media_page():
    result = _extract("media_like.html")
    assert result.published_at is not None
    assert result.title == "产业创新应用大赛开始报名"


def test_insufficient_content():
    result = _extract("empty_shell.html")
    assert result.extraction_status == ExtractionStatus.INSUFFICIENT_CONTENT
    assert not result.text
    assert "possible_dynamic_page" in result.warnings
