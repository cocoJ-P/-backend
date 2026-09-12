"""Amount candidates. Returns every explicit amount; does not pick a final value."""

import re

from app.domains.intelligence.enums import AmountKind
from app.domains.intelligence.rules.collector import RuleCollector
from app.domains.intelligence.rules.schemas import AmountCandidate
from app.domains.intelligence.schemas import ContentIntelligenceInput

AMOUNT_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>亿元|万元|元)")
KIND_WINDOW = 12
UNIT_TO_YUAN = {"元": 1.0, "万元": 10_000.0, "亿元": 100_000_000.0}


def _kind_from_prefix(prefix: str) -> AmountKind:
    if "注册资本" in prefix:
        return AmountKind.UNKNOWN
    if "奖" in prefix:
        return AmountKind.AWARD
    if "贷款" in prefix:
        return AmountKind.LOAN
    if "融资" in prefix:
        return AmountKind.FINANCING
    if "补贴" in prefix:
        return AmountKind.SUBSIDY
    if "支持" in prefix:
        return AmountKind.FUNDING
    return AmountKind.UNKNOWN


def apply_amount_rules(payload: ContentIntelligenceInput, collector: RuleCollector) -> None:
    text = payload.normalized_text
    for match in AMOUNT_RE.finditer(text):
        unit = match.group("unit")
        number = float(match.group("num"))
        amount = number * UNIT_TO_YUAN[unit]
        prefix = text[max(0, match.start() - KIND_WINDOW) : match.start()]
        kind = _kind_from_prefix(prefix)
        evidence_id = collector.add_text_evidence(
            text,
            match.start(),
            match.end(),
            field="amount_candidate",
        )
        collector.amount_candidates.append(
            AmountCandidate(
                raw_text=match.group(0),
                amount=amount,
                currency="CNY",
                unit="元",
                kind=kind,
                evidence_id=evidence_id,
            )
        )
