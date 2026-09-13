"""Normalize compatible-model JSON before ContentIntelligenceResult validation."""

from __future__ import annotations

from typing import Any

from app.core.time import to_iso8601, utc_now
from app.domains.intelligence.contracts import FORBIDDEN_OUTPUT_FIELDS, SCHEMA_VERSION
from app.domains.intelligence.llm.prompts import INTELLIGENCE_PROMPT_VERSION

_ROOT_KEYS = (
    "analysis",
    "source_assessment",
    "opportunity_claim",
    "evidence",
    "metadata",
)
_ANALYSIS_KEYS = ("content_nature", "opportunity_relevance", "confidence", "warnings")
_SOURCE_KEYS = (
    "apparent_source_type",
    "marketing_level",
    "marketing_signals",
    "intermediary_level",
    "intermediary_signals",
    "originality_claim",
)
_CLAIM_KEYS = (
    "claimed_type",
    "claimed_title",
    "claimed_issuer",
    "claimed_region",
    "claimed_publish_date",
    "claimed_deadline",
    "claimed_status",
    "claimed_summary",
    "claimed_resource_value",
    "claimed_requirements",
    "claimed_required_materials",
    "claimed_application_process",
    "claimed_official_url",
    "claim_confidence",
)
_RESOURCE_KEYS = ("funding", "scenario", "financing", "service", "other")
_FUNDING_KEYS = ("description", "amount", "currency", "amount_type")
_REQUIREMENT_KEYS = (
    "key",
    "label",
    "operator",
    "expected_value",
    "required",
    "description",
    "confidence",
    "evidence_ids",
)
_EVIDENCE_KEYS = ("id", "kind", "field", "text", "source")
_METADATA_KEYS = ("schema_version", "analyzer_version", "created_at")

_ENUM_FALLBACKS = {
    ("analysis", "content_nature"): {
        "opportunity_announcement",
        "opportunity_interpretation",
        "news_report",
        "marketing_content",
        "service_content",
        "general_information",
        "mixed",
        "unknown",
    },
    ("analysis", "opportunity_relevance"): {"high", "medium", "low", "none", "unknown"},
    ("source_assessment", "apparent_source_type"): {
        "official_like",
        "media_like",
        "service_provider_like",
        "individual_like",
        "unknown",
    },
    ("source_assessment", "marketing_level"): {"none", "low", "medium", "high", "unknown"},
    ("source_assessment", "intermediary_level"): {"none", "possible", "likely", "unknown"},
    ("source_assessment", "originality_claim"): {
        "claims_original",
        "appears_repost",
        "appears_interpretation",
        "unclear",
    },
}


def sanitize_llm_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = _unwrap_root(data)
    payload = _strip_forbidden(payload)
    if not isinstance(payload, dict):
        return {}
    cleaned: dict[str, Any] = {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    cleaned["analysis"] = {**_default_analysis(), **_pick(analysis, _ANALYSIS_KEYS)}
    _coerce_enum(cleaned["analysis"], "content_nature", "unknown")
    _coerce_enum(cleaned["analysis"], "opportunity_relevance", "unknown")
    _coerce_float(cleaned["analysis"], "confidence")
    if not isinstance(cleaned["analysis"].get("warnings"), list):
        cleaned["analysis"]["warnings"] = []
    if not analysis:
        cleaned["analysis"]["warnings"] = list(cleaned["analysis"]["warnings"]) + [
            "insufficient_context"
        ]

    source = payload.get("source_assessment") if isinstance(payload.get("source_assessment"), dict) else {}
    cleaned["source_assessment"] = {**_default_source(), **_pick(source, _SOURCE_KEYS)}
    _coerce_enum(cleaned["source_assessment"], "apparent_source_type", "unknown")
    _coerce_enum(cleaned["source_assessment"], "marketing_level", "unknown")
    _coerce_enum(cleaned["source_assessment"], "intermediary_level", "unknown")
    _coerce_enum(cleaned["source_assessment"], "originality_claim", "unclear")
    for key in ("marketing_signals", "intermediary_signals"):
        if not isinstance(cleaned["source_assessment"].get(key), list):
            cleaned["source_assessment"][key] = []
    claim = payload.get("opportunity_claim")
    if claim in ({}, "", []):
        cleaned["opportunity_claim"] = None
    elif isinstance(claim, dict):
        cleaned["opportunity_claim"] = _sanitize_claim(claim)
    evidence = payload.get("evidence")
    if isinstance(evidence, list):
        cleaned["evidence"] = [_pick(item, _EVIDENCE_KEYS) for item in evidence if isinstance(item, dict)]
        for item in cleaned["evidence"]:
            text = item.get("text")
            if isinstance(text, str) and len(text) > 300:
                item["text"] = text[:300]
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    cleaned["metadata"] = _pick(metadata, _METADATA_KEYS)
    cleaned["metadata"].setdefault("schema_version", SCHEMA_VERSION)
    cleaned["metadata"].setdefault("analyzer_version", INTELLIGENCE_PROMPT_VERSION)
    if not cleaned["metadata"].get("created_at"):
        cleaned["metadata"]["created_at"] = to_iso8601(utc_now())
    return cleaned


def _unwrap_root(data: dict[str, Any]) -> dict[str, Any]:
    if any(key in data for key in _ROOT_KEYS):
        return data
    for key in ("result", "data", "output"):
        nested = data.get(key)
        if isinstance(nested, dict) and any(item in nested for item in _ROOT_KEYS):
            return nested
    return data


def _sanitize_claim(claim: dict[str, Any]) -> dict[str, Any]:
    cleaned = _pick(claim, _CLAIM_KEYS)
    for key in ("claimed_publish_date", "claimed_deadline", "claimed_title", "claimed_issuer"):
        if cleaned.get(key) == "":
            cleaned[key] = None
    _coerce_float(cleaned, "claim_confidence")
    resource = cleaned.get("claimed_resource_value")
    if isinstance(resource, dict):
        cleaned["claimed_resource_value"] = _pick(resource, _RESOURCE_KEYS)
        funding = cleaned["claimed_resource_value"].get("funding")
        if isinstance(funding, dict):
            cleaned["claimed_resource_value"]["funding"] = _pick(funding, _FUNDING_KEYS)
            _coerce_float(cleaned["claimed_resource_value"]["funding"], "amount")
    requirements = cleaned.get("claimed_requirements")
    if isinstance(requirements, list):
        cleaned["claimed_requirements"] = [
            _pick(item, _REQUIREMENT_KEYS) for item in requirements if isinstance(item, dict)
        ]
        for item in cleaned["claimed_requirements"]:
            _coerce_float(item, "confidence")
            if not isinstance(item.get("evidence_ids"), list):
                item["evidence_ids"] = []
    for key in ("claimed_required_materials", "claimed_application_process"):
        if not isinstance(cleaned.get(key), list):
            cleaned[key] = []
    return cleaned


def _default_analysis() -> dict[str, Any]:
    return {
        "content_nature": "unknown",
        "opportunity_relevance": "unknown",
        "confidence": 0.0,
        "warnings": [],
    }


def _default_source() -> dict[str, Any]:
    return {
        "apparent_source_type": "unknown",
        "marketing_level": "unknown",
        "marketing_signals": [],
        "intermediary_level": "unknown",
        "intermediary_signals": [],
        "originality_claim": "unclear",
    }


def _pick(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: payload[key] for key in keys if key in payload}


def _strip_forbidden(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_forbidden(item)
            for key, item in value.items()
            if key not in FORBIDDEN_OUTPUT_FIELDS
        }
    if isinstance(value, list):
        return [_strip_forbidden(item) for item in value]
    return value


def _coerce_enum(payload: dict[str, Any], key: str, fallback: str) -> None:
    value = payload.get(key)
    if value is None:
        return
    if not isinstance(value, str) or value not in _enum_values(key):
        payload[key] = fallback


def _enum_values(key: str) -> set[str]:
    for (_, field), values in _ENUM_FALLBACKS.items():
        if field == key:
            return values
    return set()


def _coerce_float(payload: dict[str, Any], key: str) -> None:
    value = payload.get(key)
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        return
    if isinstance(value, str):
        try:
            payload[key] = float(value)
        except ValueError:
            return
