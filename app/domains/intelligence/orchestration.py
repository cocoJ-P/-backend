"""Opportunity Intelligence pipeline orchestration.

Reads OpportunitySource / IngestedContent, runs RuleAnalyzer then
LLMIntelligenceAnalyzer, and persists an IntelligenceRun.

A succeeded run means analysis completed. It does not verify the opportunity.
This orchestrator does not create Opportunity records or mutate sources.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException, NotFoundException
from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.intelligence import repository as run_repository
from app.domains.intelligence.api_schemas import IntelligenceAnalysisExecution, IntelligenceRunResponse
from app.domains.intelligence.enums import IntelligenceRunStatus
from app.domains.intelligence.fingerprint import compute_analysis_fingerprint, compute_input_hash
from app.domains.intelligence.llm.analyzer import LLMIntelligenceAnalyzer
from app.domains.intelligence.llm.prompt_builder import INPUT_TRUNCATED_WARNING
from app.domains.intelligence.llm.prompts import INTELLIGENCE_PROMPT_VERSION
from app.domains.intelligence.models import IntelligenceRun
from app.domains.intelligence.rules.analyzer import RuleAnalyzer
from app.domains.intelligence.rules.schemas import RULE_VERSION, RuleAnalysisResult
from app.domains.intelligence.schemas import ContentIntelligenceInput, ContentIntelligenceResult
from app.domains.opportunity.models import OpportunitySource
from app.domains.opportunity.repository import get_source as get_opportunity_source
from app.integrations.content.models import IngestedContent
from app.integrations.content.repository import get_by_id as get_ingestion_by_id
from app.integrations.content.repository import list_by_source
from app.integrations.content.schemas import ExtractionStatus
from app.integrations.llm.base import LLMProvider
from app.integrations.llm.errors import (
    LLMProviderError,
    LLMRateLimitError,
    LLMSchemaValidationError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.integrations.llm.factory import create_llm_provider

logger = get_logger(__name__)

ERROR_MESSAGE_MAX_CHARS = 1000
SOURCE_EXTRACTION_PARTIAL_WARNING = "source_extraction_partial"
ANALYZABLE_EXTRACTION_STATUSES = {
    ExtractionStatus.SUCCESS.value,
    ExtractionStatus.PARTIAL.value,
    ExtractionStatus.NOT_REQUIRED.value,
}


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def is_analyzable(ingestion: IngestedContent) -> bool:
    text = ingestion.normalized_text or ""
    if not text.strip():
        return False
    return ingestion.extraction_status in ANALYZABLE_EXTRACTION_STATUSES


def build_content_intelligence_input(
    source: OpportunitySource,
    ingestion: IngestedContent,
) -> ContentIntelligenceInput:
    text = ingestion.normalized_text or ""
    return ContentIntelligenceInput(
        source_id=source.id,
        ingestion_id=ingestion.id,
        title=ingestion.raw_title or source.title,
        publisher=ingestion.raw_publisher or source.publisher,
        source_url=ingestion.resolved_url or source.url,
        published_at=ingestion.raw_published_at or source.published_at,
        normalized_text=text,
    )


def load_intelligence_result(run: IntelligenceRun) -> ContentIntelligenceResult | None:
    if not run.intelligence_result_json:
        return None
    return ContentIntelligenceResult.model_validate(run.intelligence_result_json)


def load_rule_result(run: IntelligenceRun) -> RuleAnalysisResult | None:
    if not run.rule_result_json:
        return None
    return RuleAnalysisResult.model_validate(run.rule_result_json)


def _safe_error_message(message: str) -> str:
    text = message or ""
    secret = (settings.LLM_API_KEY or "").strip()
    if secret:
        text = text.replace(secret, "[redacted]")
    text = text.replace("Authorization", "[redacted]")
    return text[:ERROR_MESSAGE_MAX_CHARS]


class OpportunityIntelligenceOrchestrator:
    def __init__(self, db: Session, provider: LLMProvider | None = None) -> None:
        self.db = db
        self._provider = provider

    def analyze_source(
        self,
        source_id: UUID,
        ingestion_id: UUID | None = None,
        force: bool = False,
    ) -> IntelligenceAnalysisExecution:
        source_id = _as_uuid(source_id)
        source = get_opportunity_source(self.db, source_id)
        if source is None:
            raise NotFoundException(
                "Opportunity source not found",
                code="OPPORTUNITY_SOURCE_NOT_FOUND",
            )
        ingestion = self._select_ingestion(
            source_id,
            None if ingestion_id is None else _as_uuid(ingestion_id),
        )
        payload = build_content_intelligence_input(source, ingestion)
        input_hash = compute_input_hash(
            title=payload.title,
            publisher=payload.publisher,
            source_url=payload.source_url,
            published_at=payload.published_at,
            normalized_text=payload.normalized_text,
        )
        provider_name = (settings.LLM_PROVIDER or "").strip().lower()
        model_name = settings.LLM_MODEL
        fingerprint = compute_analysis_fingerprint(
            input_hash=input_hash,
            rule_version=RULE_VERSION,
            prompt_version=INTELLIGENCE_PROMPT_VERSION,
            provider=provider_name,
            model=model_name,
        )

        if not force:
            cached = run_repository.find_latest_succeeded_by_fingerprint(
                self.db,
                source_id=source_id,
                analysis_fingerprint=fingerprint,
            )
            if cached is not None:
                try:
                    result = load_intelligence_result(cached)
                except ValidationError:
                    result = None
                if result is not None:
                    logger.info(
                        "intelligence run reused run_id=%s source_id=%s fingerprint=%s",
                        cached.id,
                        source_id,
                        fingerprint,
                    )
                    return IntelligenceAnalysisExecution(
                        run=IntelligenceRunResponse.model_validate(cached),
                        intelligence_result=result,
                        reused=True,
                    )

        llm_provider = self._require_provider()
        truncated = len(payload.normalized_text) > settings.LLM_MAX_INPUT_CHARS
        run = IntelligenceRun(
            source_id=source.id,
            ingestion_id=ingestion.id,
            status=IntelligenceRunStatus.RUNNING.value,
            input_hash=input_hash,
            analysis_fingerprint=fingerprint,
            rule_version=RULE_VERSION,
            prompt_version=INTELLIGENCE_PROMPT_VERSION,
            provider=provider_name,
            model=model_name,
            input_char_count=len(payload.normalized_text),
            input_truncated=truncated,
            started_at=utc_now(),
        )
        run_repository.create_run(self.db, run)
        self.db.commit()

        rule_dump: dict | None = None
        try:
            rule_result = RuleAnalyzer().analyze(payload)
            rule_dump = rule_result.model_dump(mode="json")
            extraction = LLMIntelligenceAnalyzer(llm_provider).analyze(payload, rule_result)
            result = extraction.intelligence_result
            if ingestion.extraction_status == ExtractionStatus.PARTIAL.value:
                if SOURCE_EXTRACTION_PARTIAL_WARNING not in result.analysis.warnings:
                    result.analysis.warnings.append(SOURCE_EXTRACTION_PARTIAL_WARNING)
            if truncated and INPUT_TRUNCATED_WARNING not in result.analysis.warnings:
                result.analysis.warnings.append(INPUT_TRUNCATED_WARNING)

            usage = extraction.usage.model_dump(mode="json")
            usage["latency_ms"] = extraction.latency_ms
            usage["request_id"] = extraction.request_id

            run = run_repository.get_run(self.db, run.id) or run
            run_repository.mark_succeeded(
                self.db,
                run,
                rule_result_json=rule_dump,
                intelligence_result_json=result.model_dump(mode="json"),
                usage_json=usage,
                provider=extraction.provider,
                model=extraction.model,
                completed_at=utc_now(),
            )
            self.db.commit()
            run = run_repository.get_run(self.db, run.id) or run
            logger.info(
                "intelligence run succeeded run_id=%s source_id=%s ingestion_id=%s provider=%s model=%s tokens=%s reused=false",
                run.id,
                source_id,
                ingestion.id,
                extraction.provider,
                extraction.model,
                usage.get("total_tokens"),
            )
            return IntelligenceAnalysisExecution(
                run=IntelligenceRunResponse.model_validate(run),
                intelligence_result=result,
                reused=False,
            )
        except Exception as exc:
            error_code, status_code, public_message = _map_pipeline_error(exc)
            self.db.rollback()
            persisted = run_repository.get_run(self.db, run.id)
            if persisted is not None:
                run_repository.mark_failed(
                    self.db,
                    persisted,
                    error_code=error_code,
                    error_message=_safe_error_message(str(exc) or public_message),
                    completed_at=utc_now(),
                    rule_result_json=rule_dump,
                )
                self.db.commit()
            logger.info(
                "intelligence run failed run_id=%s source_id=%s error_code=%s",
                run.id,
                source_id,
                error_code,
            )
            raise AppException(
                error_code,
                public_message,
                status_code=status_code,
                details={"run_id": str(run.id)},
            ) from exc

    def _select_ingestion(
        self,
        source_id: UUID,
        ingestion_id: UUID | None,
    ) -> IngestedContent:
        if ingestion_id is not None:
            record = get_ingestion_by_id(self.db, ingestion_id)
            if record is None:
                raise NotFoundException(
                    "Ingested content not found",
                    code="INGESTED_CONTENT_NOT_FOUND",
                )
            if record.source_id != source_id:
                raise AppException(
                    "INGESTION_SOURCE_MISMATCH",
                    "Ingested content does not belong to this source",
                    status_code=409,
                )
            if not is_analyzable(record):
                raise AppException(
                    "CONTENT_NOT_ANALYZABLE",
                    "Ingested content is not analyzable",
                    status_code=409,
                )
            return record

        for record in list_by_source(self.db, source_id):
            if is_analyzable(record):
                return record
        raise AppException(
            "CONTENT_NOT_ANALYZABLE",
            "No analyzable ingested content for this source",
            status_code=409,
        )

    def _require_provider(self) -> LLMProvider:
        if self._provider is not None:
            return self._provider
        name = (settings.LLM_PROVIDER or "").strip().lower()
        if name in {"openai", "openai_compatible"} and not (settings.LLM_API_KEY or "").strip():
            raise AppException(
                "LLM_NOT_CONFIGURED",
                "LLM_API_KEY is not configured",
                status_code=503,
            )
        try:
            return create_llm_provider()
        except LLMProviderError as exc:
            message = str(exc)
            if "LLM_API_KEY" in message:
                raise AppException(
                    "LLM_NOT_CONFIGURED",
                    "LLM_API_KEY is not configured",
                    status_code=503,
                ) from exc
            raise AppException(
                "LLM_PROVIDER_ERROR",
                _safe_error_message(message) or "LLM provider is not available",
                status_code=502,
            ) from exc


def _map_pipeline_error(exc: Exception) -> tuple[str, int, str]:
    if isinstance(exc, LLMTimeoutError):
        return "LLM_TIMEOUT", 504, "LLM request timed out"
    if isinstance(exc, LLMRateLimitError):
        return "LLM_RATE_LIMITED", 503, "LLM rate limit exceeded"
    if isinstance(exc, LLMSchemaValidationError):
        return "LLM_SCHEMA_VALIDATION_ERROR", 502, "LLM output failed schema validation"
    if isinstance(exc, LLMStructuredOutputError):
        return "LLM_STRUCTURED_OUTPUT_ERROR", 502, "LLM structured output was invalid"
    if isinstance(exc, LLMProviderError):
        return "LLM_PROVIDER_ERROR", 502, "LLM provider error"
    return "LLM_PROVIDER_ERROR", 502, "Intelligence analysis failed"
