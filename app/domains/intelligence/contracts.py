"""Opportunity Intelligence contract constants and semantic guards.

B4 extracts claims from content. It does not verify facts, search official
sources, or bind a model vendor.
"""

from typing import Any

SCHEMA_VERSION = "1.0"
DEFAULT_ANALYZER_VERSION = "contract-only"
EVIDENCE_TEXT_MAX_CHARS = 300

SUGGESTED_WARNING_CODES = (
    "ambiguous_deadline",
    "missing_issuer",
    "multiple_opportunities_detected",
    "insufficient_context",
    "input_truncated",
    "source_extraction_partial",
)

FORBIDDEN_OUTPUT_FIELDS = frozenset(
    {
        "verified",
        "is_verified",
        "is_official",
        "verified_official_url",
        "is_original",
        "authentic",
        "fake",
        "provenance",
        "search_results",
        "matched_opportunity_id",
        "dedup_score",
        "enterprise_match",
        "qualification_score",
        "strategic_score",
    }
)


def collect_keys(payload: Any) -> set[str]:
    keys: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                keys.add(str(key))
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return keys


def forbidden_fields_present(payload: dict[str, Any]) -> set[str]:
    return collect_keys(payload) & FORBIDDEN_OUTPUT_FIELDS
