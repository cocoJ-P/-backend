"""Validate LLM evidence against supplied content, metadata, and rule evidence."""

from __future__ import annotations

from app.core.time import to_iso8601
from app.domains.intelligence.contracts import EVIDENCE_TEXT_MAX_CHARS
from app.domains.intelligence.enums import EvidenceKind
from app.domains.intelligence.rules.schemas import RuleAnalysisResult
from app.domains.intelligence.schemas import (
    ContentIntelligenceInput,
    ContentIntelligenceResult,
    IntelligenceEvidence,
)
from app.integrations.llm.errors import LLMSchemaValidationError


def _collapsed(value: str) -> str:
    return "".join(value.split())


def _appears_in(needle: str, haystack: str) -> bool:
    if not needle.strip():
        return False
    if needle in haystack:
        return True
    collapsed_needle = _collapsed(needle)
    collapsed_haystack = _collapsed(haystack)
    return bool(collapsed_needle) and collapsed_needle in collapsed_haystack


def _metadata_corpus(payload: ContentIntelligenceInput) -> list[str]:
    values: list[str] = []
    for item in (payload.title, payload.publisher, payload.source_url):
        if item and item.strip():
            values.append(item.strip())
    if payload.published_at is not None:
        values.append(to_iso8601(payload.published_at))
        values.append(payload.published_at.isoformat())
        values.append(payload.published_at.date().isoformat())
    return values


def _metadata_matches(text: str, payload: ContentIntelligenceInput) -> bool:
    return any(_appears_in(value, text) or _appears_in(text, value) for value in _metadata_corpus(payload))


def validate_evidence_against_input(
    result: ContentIntelligenceResult,
    payload: ContentIntelligenceInput,
    rules: RuleAnalysisResult,
) -> None:
    rule_by_id = {item.id: item for item in rules.evidence}
    known_result_ids = {item.id for item in result.evidence}

    referenced: list[str] = []
    if result.opportunity_claim is not None:
        for requirement in result.opportunity_claim.claimed_requirements:
            referenced.extend(requirement.evidence_ids)

    for evidence_id in referenced:
        if evidence_id not in known_result_ids:
            raise LLMSchemaValidationError(
                "requirement references unknown evidence_id",
                details={"evidence_id": evidence_id},
            )
        if evidence_id.startswith("rule_ev_") and evidence_id not in rule_by_id:
            raise LLMSchemaValidationError(
                "requirement references missing rule evidence",
                details={"evidence_id": evidence_id},
            )

    for item in result.evidence:
        if len(item.text) > EVIDENCE_TEXT_MAX_CHARS:
            raise LLMSchemaValidationError(
                "evidence exceeds 300 characters",
                details={"evidence_id": item.id},
            )
        if item.id.startswith("rule_ev_"):
            if item.id not in rule_by_id:
                raise LLMSchemaValidationError(
                    "unknown rule evidence id",
                    details={"evidence_id": item.id},
                )
            continue
        if item.kind == EvidenceKind.DIRECT_QUOTE:
            in_body = _appears_in(item.text, payload.normalized_text)
            in_title = bool(payload.title) and _appears_in(item.text, payload.title or "")
            if not in_body and not in_title:
                raise LLMSchemaValidationError(
                    "direct_quote evidence was not found in the supplied content",
                    details={"evidence_id": item.id},
                )
        elif item.kind == EvidenceKind.METADATA:
            if not _metadata_matches(item.text, payload):
                raise LLMSchemaValidationError(
                    "metadata evidence does not match supplied metadata",
                    details={"evidence_id": item.id},
                )
        elif item.kind == EvidenceKind.DERIVED_SIGNAL:
            rule_texts = {entry.text for entry in rules.evidence}
            if item.text not in rule_texts and not _appears_in(item.text, payload.normalized_text):
                raise LLMSchemaValidationError(
                    "derived_signal evidence could not be verified",
                    details={"evidence_id": item.id},
                )


def rewrite_evidence_ids(
    result: ContentIntelligenceResult,
    rules: RuleAnalysisResult,
) -> ContentIntelligenceResult:
    """Keep authentic rule_ev_* ids; assign llm_ev_* to model-created evidence."""
    rule_by_id = {item.id: item for item in rules.evidence}
    remapped: list[IntelligenceEvidence] = []
    id_map: dict[str, str] = {}
    seq = 0
    seen: set[str] = set()

    for item in result.evidence:
        if item.id in rule_by_id:
            canonical = rule_by_id[item.id]
            new_id = canonical.id
            replacement = canonical
        else:
            seq += 1
            new_id = f"llm_ev_{seq:03d}"
            replacement = item.model_copy(update={"id": new_id})
        id_map[item.id] = new_id
        if new_id not in seen:
            remapped.append(replacement)
            seen.add(new_id)

    claim = result.opportunity_claim
    if claim is not None:
        new_requirements = []
        for requirement in claim.claimed_requirements:
            mapped_ids = [id_map.get(item, item) for item in requirement.evidence_ids]
            new_requirements.append(requirement.model_copy(update={"evidence_ids": mapped_ids}))
        claim = claim.model_copy(update={"claimed_requirements": new_requirements})

    return result.model_copy(update={"evidence": remapped, "opportunity_claim": claim})
