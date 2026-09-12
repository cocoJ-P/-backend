"""Structural observations: contacts, CTA-like prompts, countable methods."""

import re

from app.domains.intelligence.enums import SignalCategory, SignalStrength
from app.domains.intelligence.rules.collector import RuleCollector
from app.domains.intelligence.schemas import ContentIntelligenceInput

MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
LANDLINE_RE = re.compile(r"(?<!\d)0\d{2,3}-\d{7,8}(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
WECHAT_RE = re.compile(r"添加微信|微信号|加微信")
QR_RE = re.compile(r"扫描二维码|二维码|扫码")


def _add_span_signal(
    collector: RuleCollector,
    text: str,
    match: re.Match[str],
    *,
    code: str,
    strength: SignalStrength,
    description: str,
) -> None:
    evidence_id = collector.add_text_evidence(
        text,
        match.start(),
        match.end(),
        field=code,
    )
    collector.add_signal(
        code=code,
        category=SignalCategory.STRUCTURE,
        strength=strength,
        description=description,
        evidence_id=evidence_id,
    )


def apply_structural_rules(payload: ContentIntelligenceInput, collector: RuleCollector) -> None:
    text = payload.normalized_text
    phones = list(MOBILE_RE.finditer(text)) + list(LANDLINE_RE.finditer(text))
    emails = list(EMAIL_RE.finditer(text))
    wechat = list(WECHAT_RE.finditer(text))
    qr = list(QR_RE.finditer(text))

    contact_matches = [*phones, *emails, *wechat, *qr]
    for match in contact_matches:
        _add_span_signal(
            collector,
            text,
            match,
            code="structure.contact_information_present",
            strength=SignalStrength.MEDIUM,
            description="Detected observable contact information",
        )

    method_types = 0
    if phones:
        method_types += 1
    if emails:
        method_types += 1
    if wechat:
        method_types += 1
    if qr:
        method_types += 1
    contact_items = len(phones) + len(emails) + len(wechat) + len(qr)
    if method_types >= 2 or contact_items >= 2:
        first = contact_matches[0]
        _add_span_signal(
            collector,
            text,
            first,
            code="structure.multiple_contact_methods",
            strength=SignalStrength.MEDIUM,
            description="Detected more than one contact method",
        )
