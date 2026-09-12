"""URL candidates from existing text and metadata. No fetching."""

import re
from urllib.parse import urlparse

from app.domains.intelligence.enums import (
    EvidenceKind,
    SignalCategory,
    SignalStrength,
    URLCandidateKind,
)
from app.domains.intelligence.rules.collector import RuleCollector
from app.domains.intelligence.rules.schemas import URLCandidate
from app.domains.intelligence.schemas import ContentIntelligenceInput

URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
DOCUMENT_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")
TRAILING_PUNCT = ".,;:)]}>\"'。，、）；」』"


def _clean_url(raw: str) -> str:
    url = raw.strip()
    while url and url[-1] in TRAILING_PUNCT:
        url = url[:-1]
    return url


def is_gov_cn_host(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    return normalized == "gov.cn" or normalized.endswith(".gov.cn")


def classify_url(url: str, source_url: str | None) -> URLCandidateKind:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if is_gov_cn_host(host):
        return URLCandidateKind.OFFICIAL_DOMAIN_LIKE
    if any(path.endswith(suffix) for suffix in DOCUMENT_SUFFIXES):
        return URLCandidateKind.DOCUMENT_LINK
    if source_url:
        source_host = (urlparse(source_url).hostname or "").lower()
        if source_host and host and source_host == host:
            return URLCandidateKind.SAME_PAGE
    if host:
        return URLCandidateKind.EXTERNAL_LINK
    return URLCandidateKind.UNKNOWN


def apply_url_rules(payload: ContentIntelligenceInput, collector: RuleCollector) -> None:
    seen: set[str] = set()

    if payload.source_url:
        cleaned = _clean_url(payload.source_url)
        if cleaned:
            seen.add(cleaned)
            evidence_id = collector.add_literal_evidence(
                cleaned,
                field="url_candidate",
                kind=EvidenceKind.METADATA,
            )
            collector.url_candidates.append(
                URLCandidate(
                    url=cleaned,
                    kind=classify_url(cleaned, cleaned),
                    source="metadata",
                    evidence_id=evidence_id,
                )
            )

    text = payload.normalized_text
    for match in URL_RE.finditer(text):
        cleaned = _clean_url(match.group(0))
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        kind = classify_url(cleaned, payload.source_url)
        evidence_id = collector.add_text_evidence(
            text,
            match.start(),
            match.end(),
            field="url_candidate",
        )
        collector.url_candidates.append(
            URLCandidate(
                url=cleaned,
                kind=kind,
                source="normalized_text",
                evidence_id=evidence_id,
            )
        )
        if kind == URLCandidateKind.OFFICIAL_DOMAIN_LIKE:
            collector.add_signal(
                code="structure.external_official_link",
                category=SignalCategory.STRUCTURE,
                strength=SignalStrength.MEDIUM,
                description="Detected a gov.cn domain-like URL; not a verified official source",
                evidence_id=evidence_id,
            )
