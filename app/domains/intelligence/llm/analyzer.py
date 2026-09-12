"""LLM structured extraction. Does not run RuleAnalyzer or access the database."""

from __future__ import annotations

from pydantic import ValidationError

from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.intelligence.contracts import SCHEMA_VERSION, forbidden_fields_present
from app.domains.intelligence.llm.evidence import rewrite_evidence_ids, validate_evidence_against_input
from app.domains.intelligence.llm.prompt_builder import (
    INPUT_TRUNCATED_WARNING,
    build_repair_prompt,
    build_system_prompt,
    build_user_prompt,
    prompt_version,
)
from app.domains.intelligence.llm.prompts import INTELLIGENCE_PROMPT_VERSION
from app.domains.intelligence.llm.schemas import LLMExtractionResult
from app.domains.intelligence.rules.schemas import RuleAnalysisResult
from app.domains.intelligence.schemas import ContentIntelligenceInput, ContentIntelligenceResult
from app.integrations.llm.base import LLMProvider
from app.integrations.llm.errors import LLMProviderError, LLMSchemaValidationError
from app.integrations.llm.factory import create_llm_provider

logger = get_logger(__name__)


class LLMIntelligenceAnalyzer:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider or create_llm_provider()

    def analyze(
        self,
        payload: ContentIntelligenceInput,
        rules: RuleAnalysisResult,
    ) -> LLMExtractionResult:
        system_prompt = build_system_prompt()
        user_prompt, truncated = build_user_prompt(payload, rules)
        try:
            response = self._provider.structured_generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=ContentIntelligenceResult,
            )
            result = self._validate_and_postprocess(response.data, payload, rules, truncated)
        except LLMSchemaValidationError as exc:
            repair_prompt = build_repair_prompt(user_prompt, exc)
            try:
                response = self._provider.structured_generate(
                    system_prompt=system_prompt,
                    user_prompt=repair_prompt,
                    response_model=ContentIntelligenceResult,
                )
                result = self._validate_and_postprocess(response.data, payload, rules, truncated)
            except LLMSchemaValidationError:
                raise
            except LLMProviderError:
                raise exc from None
        except LLMProviderError:
            logger.info(
                "llm extraction failed provider=%s prompt_version=%s",
                getattr(self._provider, "model", None),
                prompt_version(),
            )
            raise
        except Exception as exc:
            raise LLMProviderError(
                "unexpected LLM provider failure",
                details={"type": type(exc).__name__},
            ) from exc

        logger.info(
            "llm extraction succeeded provider=%s model=%s prompt_version=%s latency_ms=%s tokens=%s",
            response.provider,
            response.model,
            prompt_version(),
            response.latency_ms,
            response.usage.total_tokens,
        )
        return LLMExtractionResult(
            intelligence_result=result,
            usage=response.usage,
            provider=response.provider,
            model=response.model,
            prompt_version=INTELLIGENCE_PROMPT_VERSION,
            request_id=response.request_id,
            latency_ms=response.latency_ms,
        )

    def _validate_and_postprocess(
        self,
        data: object,
        payload: ContentIntelligenceInput,
        rules: RuleAnalysisResult,
        truncated: bool,
    ) -> ContentIntelligenceResult:
        if not isinstance(data, dict):
            raise LLMSchemaValidationError("LLM output root must be an object")
        forbidden = forbidden_fields_present(data)
        if forbidden:
            raise LLMSchemaValidationError(
                "LLM output contained forbidden fields",
                details={"fields": sorted(forbidden)},
            )
        try:
            result = ContentIntelligenceResult.model_validate(data)
        except ValidationError as exc:
            raise LLMSchemaValidationError(
                "LLM output failed Pydantic validation",
                details=exc.errors(),
            ) from exc

        validate_evidence_against_input(result, payload, rules)
        result = rewrite_evidence_ids(result, rules)
        result.metadata.schema_version = SCHEMA_VERSION
        result.metadata.analyzer_version = INTELLIGENCE_PROMPT_VERSION
        result.metadata.created_at = utc_now()
        if truncated and INPUT_TRUNCATED_WARNING not in result.analysis.warnings:
            result.analysis.warnings.append(INPUT_TRUNCATED_WARNING)
        return result
