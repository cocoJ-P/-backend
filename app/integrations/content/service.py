"""Content ingestion orchestration."""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import get_logger
from app.domains.opportunity.enums import SourceType
from app.domains.opportunity.models import OpportunitySource
from app.domains.opportunity.repository import add_source
from app.integrations.content.extractor import HtmlExtractor
from app.integrations.content.fetcher import UrlFetcher
from app.integrations.content.models import IngestedContent
from app.integrations.content.normalizer import make_excerpt, normalize_text
from app.integrations.content import repository as ingestion_repository
from app.integrations.content.schemas import (
    ExtractionStatus,
    FetchStatus,
    IngestRequest,
    IngestResponse,
    InputType,
    NormalizedContent,
)

logger = get_logger(__name__)


def ingest(
    db: Session,
    payload: IngestRequest,
    *,
    fetcher: UrlFetcher | None = None,
    extractor: HtmlExtractor | None = None,
) -> IngestResponse:
    if payload.content is None or not str(payload.content).strip():
        raise AppException(
            "INVALID_CONTENT_INPUT",
            "Content input is empty",
            status_code=400,
        )
    if payload.content_type == InputType.TEXT:
        normalized = normalize_text(payload.content)
    elif payload.content_type == InputType.URL:
        normalized = _ingest_url(
            payload.content.strip(),
            fetcher=fetcher or UrlFetcher(),
            extractor=extractor or HtmlExtractor(),
        )
    else:
        raise AppException(
            "INVALID_CONTENT_INPUT",
            "content_type must be url or text",
            status_code=400,
        )

    logger.info(
        "Ingestion completed input_type=%s fetch=%s extraction=%s http_status=%s text_len=%s",
        normalized.input_type,
        normalized.fetch_status,
        normalized.extraction_status,
        normalized.http_status,
        len(normalized.text or ""),
    )
    return _persist(db, normalized)


def _ingest_url(
    url: str,
    *,
    fetcher: UrlFetcher,
    extractor: HtmlExtractor,
) -> NormalizedContent:
    fetched = fetcher.fetch(url)
    content_type = fetched.content_type
    warnings: list[str] = []

    if content_type == "application/pdf":
        return NormalizedContent(
            input_type=InputType.URL,
            original_input=url,
            source_url=url,
            resolved_url=fetched.resolved_url,
            content_type=content_type,
            title=None,
            publisher=None,
            published_at=None,
            text=None,
            excerpt=None,
            fetch_status=FetchStatus.UNSUPPORTED_CONTENT_TYPE,
            extraction_status=ExtractionStatus.UNSUPPORTED,
            http_status=fetched.status_code,
            warnings=["pdf_not_parsed"],
        )

    if content_type not in {"text/html", "text/plain", None}:
        return NormalizedContent(
            input_type=InputType.URL,
            original_input=url,
            source_url=url,
            resolved_url=fetched.resolved_url,
            content_type=content_type,
            title=None,
            publisher=None,
            published_at=None,
            text=None,
            excerpt=None,
            fetch_status=FetchStatus.UNSUPPORTED_CONTENT_TYPE,
            extraction_status=ExtractionStatus.UNSUPPORTED,
            http_status=fetched.status_code,
            warnings=["unsupported_content_type"],
        )

    decoded = fetched.body.decode("utf-8", errors="replace")
    if content_type == "text/plain":
        from app.integrations.content.cleaner import clean_text

        text = clean_text(decoded)
        if len(text) < settings.CONTENT_MIN_TEXT_LENGTH:
            warnings.append("short_content")
        return NormalizedContent(
            input_type=InputType.URL,
            original_input=url,
            source_url=url,
            resolved_url=fetched.resolved_url,
            content_type="text/plain",
            title=None,
            publisher=None,
            published_at=None,
            text=text or None,
            excerpt=make_excerpt(text) if text else None,
            fetch_status=FetchStatus.SUCCESS,
            extraction_status=ExtractionStatus.NOT_REQUIRED,
            http_status=fetched.status_code,
            warnings=warnings,
        )

    extracted = extractor.extract(decoded, url=fetched.resolved_url)
    return NormalizedContent(
        input_type=InputType.URL,
        original_input=url,
        source_url=url,
        resolved_url=fetched.resolved_url,
        content_type="text/html",
        title=extracted.title,
        publisher=extracted.publisher,
        published_at=extracted.published_at,
        text=extracted.text,
        excerpt=make_excerpt(extracted.text),
        fetch_status=FetchStatus.SUCCESS,
        extraction_status=extracted.extraction_status,
        http_status=fetched.status_code,
        warnings=extracted.warnings,
    )


def _persist(db: Session, normalized: NormalizedContent) -> IngestResponse:
    source = OpportunitySource(
        opportunity_id=None,
        source_type=SourceType.UNKNOWN.value,
        title=normalized.title,
        publisher=normalized.publisher,
        url=normalized.resolved_url or normalized.source_url,
        published_at=normalized.published_at,
        content_excerpt=normalized.excerpt,
    )
    add_source(db, source)
    record = IngestedContent(
        source_id=source.id,
        input_type=normalized.input_type.value,
        source_url=normalized.source_url,
        resolved_url=normalized.resolved_url,
        content_type=normalized.content_type,
        raw_title=normalized.title,
        raw_publisher=normalized.publisher,
        raw_published_at=normalized.published_at,
        normalized_text=normalized.text,
        fetch_status=normalized.fetch_status.value,
        extraction_status=normalized.extraction_status.value,
        http_status=normalized.http_status,
        warnings=normalized.warnings,
    )
    ingestion_repository.add_ingested_content(db, record)
    db.commit()
    db.refresh(source)
    db.refresh(record)
    return IngestResponse(
        normalized_content=normalized,
        source=source,
        ingestion=record,
    )
