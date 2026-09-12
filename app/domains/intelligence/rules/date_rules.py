"""Exact and fuzzy date candidates. Does not derive deadlines from published_at."""

import re
from datetime import date

from app.domains.intelligence.enums import DateCandidateKind
from app.domains.intelligence.rules.collector import RuleCollector
from app.domains.intelligence.rules.schemas import DateCandidate
from app.domains.intelligence.schemas import ContentIntelligenceInput

CHINESE_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
DASH_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
SLASH_DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
FUZZY_DATE_RE = re.compile(r"本月底|下周五|下周|近期|\d{1,2}月底")
EXACT_DATE_RES = (CHINESE_DATE_RE, DASH_DATE_RE, SLASH_DATE_RE)

DEADLINE_HINTS = ("申报截止", "报名截止", "截止日期", "截止时间", "截止", "截至")
START_HINTS = ("开始时间", "起始日期", "开始")
END_HINTS = ("结束时间", "结束")
CONTEXT_WINDOW = 24


def _parse_ymd(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _kind_from_context(text: str, start: int) -> DateCandidateKind:
    window = text[max(0, start - CONTEXT_WINDOW) : start]
    for hint in DEADLINE_HINTS:
        if hint in window:
            return DateCandidateKind.DEADLINE
    for hint in START_HINTS:
        if hint in window:
            return DateCandidateKind.START_DATE
    for hint in END_HINTS:
        if hint in window:
            return DateCandidateKind.END_DATE
    return DateCandidateKind.UNKNOWN


def _add_exact(text: str, match: re.Match[str], collector: RuleCollector) -> None:
    parsed = _parse_ymd(match.group(1), match.group(2), match.group(3))
    if parsed is None:
        return
    kind = _kind_from_context(text, match.start())
    evidence_id = collector.add_text_evidence(
        text,
        match.start(),
        match.end(),
        field="date_candidate",
    )
    collector.date_candidates.append(
        DateCandidate(
            value=parsed,
            kind=kind,
            raw_text=match.group(0),
            confidence=1.0,
            evidence_id=evidence_id,
        )
    )


def apply_date_rules(payload: ContentIntelligenceInput, collector: RuleCollector) -> None:
    text = payload.normalized_text
    occupied: list[tuple[int, int]] = []
    for pattern in EXACT_DATE_RES:
        for match in pattern.finditer(text):
            occupied.append((match.start(), match.end()))
            _add_exact(text, match, collector)

    def overlaps_exact(start: int, end: int) -> bool:
        return any(start < right and end > left for left, right in occupied)

    for match in FUZZY_DATE_RE.finditer(text):
        if overlaps_exact(match.start(), match.end()):
            continue
        kind = _kind_from_context(text, match.start())
        evidence_id = collector.add_text_evidence(
            text,
            match.start(),
            match.end(),
            field="date_candidate",
        )
        collector.date_candidates.append(
            DateCandidate(
                value=None,
                kind=kind,
                raw_text=match.group(0),
                confidence=0.0,
                evidence_id=evidence_id,
            )
        )
