"""HTML main-content extraction adapter around Trafilatura."""

from __future__ import annotations

from datetime import datetime

import trafilatura
from bs4 import BeautifulSoup

from app.core.config import settings
from app.integrations.content.cleaner import clean_text
from app.integrations.content.metadata import extract_metadata, parse_published_at
from app.integrations.content.schemas import ExtractedDocument, ExtractionStatus


def _looks_dynamic(html: str, text: str | None) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    visible = soup.get_text(" ", strip=True)
    root = soup.select_one("#root, #app")
    scripts = soup.find_all("script")
    short = len(visible) < settings.CONTENT_MIN_TEXT_LENGTH and len(text or "") < settings.CONTENT_MIN_TEXT_LENGTH
    return bool(short and (root or len(scripts) >= 3))


def _fallback_article_text(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("article") or soup.select_one("main")
    if node is None:
        return None
    text = clean_text(node.get_text("\n", strip=True))
    return text or None


class HtmlExtractor:
    def extract(self, html: str, *, url: str | None = None) -> ExtractedDocument:
        warnings: list[str] = []
        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
        trafilatura_meta = trafilatura.extract_metadata(html, default_url=url)
        html_meta = extract_metadata(html)

        title = html_meta.get("title") or getattr(trafilatura_meta, "title", None)
        publisher = html_meta.get("publisher") or getattr(trafilatura_meta, "author", None)
        published_at = html_meta.get("published_at")
        if published_at is None and trafilatura_meta is not None:
            published_at = parse_published_at(getattr(trafilatura_meta, "date", None))

        text = clean_text(extracted) if extracted else None
        if not text:
            text = _fallback_article_text(html)

        if not title:
            warnings.append("title_not_found")
        if not publisher:
            warnings.append("publisher_not_found")
        if published_at is None:
            warnings.append("published_at_not_found")

        if _looks_dynamic(html, text):
            warnings.append("possible_dynamic_page")

        if not text:
            status = ExtractionStatus.INSUFFICIENT_CONTENT
        elif len(text) < settings.CONTENT_MIN_TEXT_LENGTH:
            status = ExtractionStatus.INSUFFICIENT_CONTENT
            warnings.append("short_content")
        else:
            status = ExtractionStatus.SUCCESS
            if "title_not_found" in warnings or "publisher_not_found" in warnings or "published_at_not_found" in warnings:
                status = ExtractionStatus.PARTIAL

        return ExtractedDocument(
            title=title if isinstance(title, str) and title.strip() else None,
            publisher=publisher if isinstance(publisher, str) and str(publisher).strip() else None,
            published_at=published_at if isinstance(published_at, datetime) else None,
            text=text,
            extraction_status=status,
            warnings=warnings,
        )
