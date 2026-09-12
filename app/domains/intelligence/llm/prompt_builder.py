"""Build versioned prompts. Rule context is never truncated."""

from __future__ import annotations

import json

from app.core.config import settings
from app.core.time import to_iso8601
from app.domains.intelligence.llm.prompts import INTELLIGENCE_PROMPT_VERSION, SYSTEM_PROMPT
from app.domains.intelligence.rules.schemas import RuleAnalysisResult
from app.domains.intelligence.schemas import ContentIntelligenceInput
from app.integrations.llm.errors import LLMSchemaValidationError

TRUNCATION_MARKER = "\n\n[... truncated ...]\n\n"
INPUT_TRUNCATED_WARNING = "input_truncated"


def truncate_head_tail(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    marker = TRUNCATION_MARKER
    keep = max(max_chars - len(marker), 0)
    if keep == 0:
        return text[:max_chars], True
    head = keep // 2
    tail = keep - head
    return text[:head] + marker + text[-tail:], True


def _metadata_block(payload: ContentIntelligenceInput) -> dict[str, str | None]:
    published = to_iso8601(payload.published_at) if payload.published_at is not None else None
    return {
        "title": payload.title,
        "publisher": payload.publisher,
        "source_url": payload.source_url,
        "published_at": published,
    }


def _rule_block(rules: RuleAnalysisResult) -> dict:
    dumped = rules.model_dump(mode="json")
    dumped.pop("metadata", None)
    dumped["rule_version"] = rules.metadata.rule_version
    return dumped


def build_user_prompt(
    payload: ContentIntelligenceInput,
    rules: RuleAnalysisResult,
    *,
    max_input_chars: int | None = None,
) -> tuple[str, bool]:
    limit = settings.LLM_MAX_INPUT_CHARS if max_input_chars is None else max_input_chars
    text, truncated = truncate_head_tail(payload.normalized_text, limit)
    metadata = json.dumps(_metadata_block(payload), ensure_ascii=False, indent=2)
    rule_json = json.dumps(_rule_block(rules), ensure_ascii=False, indent=2)
    prompt = f"""Task
结合 metadata、正文和 Rule Layer 观察，提取当前内容声称的信息，填入 ContentIntelligenceResult。
Rule Layer 只是辅助观察，不是最终判断。

<source_metadata>
{metadata}
</source_metadata>

<source_content>
{text}
</source_content>

<rule_analysis>
{rule_json}
</rule_analysis>
"""
    return prompt, truncated


def build_repair_prompt(user_prompt: str, error: LLMSchemaValidationError) -> str:
    details = error.details if error.details is not None else error.message
    if not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False, default=str)
    if len(details) > 2000:
        details = details[:2000]
    return (
        user_prompt
        + "\n<validation_error>\n"
        + details
        + "\n</validation_error>\n"
        + "请仅根据已提供内容修正输出，使其通过 Schema 与 Evidence 校验。不要发明新事实。\n"
    )


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def prompt_version() -> str:
    return INTELLIGENCE_PROMPT_VERSION
