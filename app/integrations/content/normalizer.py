"""Turn cleaned text into NormalizedContent without network access."""

from app.core.config import settings
from app.core.exceptions import AppException
from app.integrations.content.cleaner import clean_text
from app.integrations.content.schemas import (
    ExtractionStatus,
    FetchStatus,
    InputType,
    NormalizedContent,
)


def make_excerpt(text: str | None) -> str | None:
    if not text:
        return None
    limit = settings.CONTENT_EXCERPT_LENGTH
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def normalize_text(original: str) -> NormalizedContent:
    if original is None or not str(original).strip():
        raise AppException(
            "INVALID_CONTENT_INPUT",
            "Content text is empty",
            status_code=400,
        )

    cleaned = clean_text(original)
    if not cleaned:
        raise AppException(
            "INVALID_CONTENT_INPUT",
            "Content text is empty",
            status_code=400,
        )

    warnings: list[str] = []
    if len(cleaned) < settings.CONTENT_MIN_TEXT_LENGTH:
        warnings.append("short_content")

    return NormalizedContent(
        input_type=InputType.TEXT,
        original_input=original,
        source_url=None,
        resolved_url=None,
        content_type="text/plain",
        title=None,
        publisher=None,
        published_at=None,
        text=cleaned,
        excerpt=make_excerpt(cleaned),
        fetch_status=FetchStatus.NOT_REQUIRED,
        extraction_status=ExtractionStatus.NOT_REQUIRED,
        http_status=None,
        warnings=warnings,
    )
