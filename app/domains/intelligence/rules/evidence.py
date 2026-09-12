"""Shared evidence helpers for the Rule Layer."""

from app.domains.intelligence.contracts import EVIDENCE_TEXT_MAX_CHARS
from app.domains.intelligence.enums import EvidenceKind
from app.domains.intelligence.schemas import IntelligenceEvidence

CONTEXT_CHARS = 80


def excerpt_around(text: str, start: int, end: int, pad: int = CONTEXT_CHARS) -> str:
    left = max(0, start - pad)
    right = min(len(text), end + pad)
    snippet = text[left:right].strip()
    if len(snippet) > EVIDENCE_TEXT_MAX_CHARS:
        snippet = snippet[:EVIDENCE_TEXT_MAX_CHARS].rstrip()
    return snippet or text[:EVIDENCE_TEXT_MAX_CHARS]


def make_evidence(
    *,
    evidence_id: str,
    text: str,
    field: str,
    kind: EvidenceKind = EvidenceKind.DIRECT_QUOTE,
    source: str = "rule_layer",
) -> IntelligenceEvidence:
    return IntelligenceEvidence(
        id=evidence_id,
        kind=kind,
        field=field,
        text=text[:EVIDENCE_TEXT_MAX_CHARS],
        source=source,
    )
