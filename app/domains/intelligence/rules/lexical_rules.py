"""Centralized lexical patterns. Matching is substring-based, not semantic."""

from dataclasses import dataclass

from app.domains.intelligence.enums import SignalCategory, SignalStrength
from app.domains.intelligence.rules.collector import RuleCollector
from app.domains.intelligence.rules.schemas import EntityCandidate
from app.domains.intelligence.schemas import ContentIntelligenceInput

# Conservative org suffixes only. Empty entity_candidates is preferred over noise.
_ORG_SUFFIXES = (
    "科学技术委员会",
    "经济和信息化局",
    "发展和改革委员会",
    "工业和信息化局",
)


@dataclass(frozen=True, slots=True)
class LexicalPattern:
    phrase: str
    code: str
    category: SignalCategory
    strength: SignalStrength
    description: str


MARKETING_PATTERNS: tuple[LexicalPattern, ...] = (
    LexicalPattern("立即咨询", "marketing.contact_cta", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected explicit consultation CTA"),
    LexicalPattern("立即联系", "marketing.contact_cta", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected explicit consultation CTA"),
    LexicalPattern("扫码咨询", "marketing.contact_cta", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected explicit consultation CTA"),
    LexicalPattern("免费咨询", "marketing.contact_cta", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected explicit consultation CTA"),
    LexicalPattern("联系我们", "marketing.contact_cta", SignalCategory.MARKETING, SignalStrength.MEDIUM, "Detected contact CTA"),
    LexicalPattern("专属顾问", "marketing.contact_cta", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected exclusive-advisor CTA"),
    LexicalPattern("名额有限", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected urgency language"),
    LexicalPattern("抓紧申报", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected urgency language"),
    LexicalPattern("赶紧申报", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected urgency language"),
    LexicalPattern("最后机会", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected urgency language"),
    LexicalPattern("错过再等一年", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected urgency language"),
    LexicalPattern("老板必看", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.STRONG, "Detected urgency language"),
    LexicalPattern("限时", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.MEDIUM, "Detected urgency language"),
    LexicalPattern("重磅", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.MEDIUM, "Detected urgency language"),
    LexicalPattern("速看", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.MEDIUM, "Detected urgency language"),
    LexicalPattern("错过", "marketing.urgency_language", SignalCategory.MARKETING, SignalStrength.WEAK, "Detected urgency language"),
    LexicalPattern("最高补贴", "marketing.money_highlight", SignalCategory.MARKETING, SignalStrength.MEDIUM, "Detected money-highlight phrasing"),
    LexicalPattern("最高支持", "marketing.money_highlight", SignalCategory.MARKETING, SignalStrength.WEAK, "Detected money-highlight phrasing"),
)

INTERMEDIARY_PATTERNS: tuple[LexicalPattern, ...] = (
    LexicalPattern("专业申报团队", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected application-service phrasing"),
    LexicalPattern("专业项目申报团队", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected application-service phrasing"),
    LexicalPattern("全程代办服务", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected application-service phrasing"),
    LexicalPattern("全程代办", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected application-service phrasing"),
    LexicalPattern("全程服务", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.MEDIUM, "Detected application-service phrasing"),
    LexicalPattern("材料代写", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected application-service phrasing"),
    LexicalPattern("材料撰写", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.MEDIUM, "Detected application-service phrasing"),
    LexicalPattern("项目包装", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected application-service phrasing"),
    LexicalPattern("申报辅导", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected application-service phrasing"),
    LexicalPattern("申报服务", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.MEDIUM, "Detected application-service phrasing"),
    LexicalPattern("代申报", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected application-service phrasing"),
    LexicalPattern("代办", "intermediary.application_service", SignalCategory.INTERMEDIARY, SignalStrength.MEDIUM, "Detected application-service phrasing"),
    LexicalPattern("项目顾问", "intermediary.consultant_contact", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected consultant-contact phrasing"),
    LexicalPattern("联系顾问", "intermediary.consultant_contact", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected consultant-contact phrasing"),
    LexicalPattern("提高通过率", "intermediary.success_claim", SignalCategory.INTERMEDIARY, SignalStrength.STRONG, "Detected success-claim phrasing"),
    LexicalPattern("成功申报", "intermediary.success_claim", SignalCategory.INTERMEDIARY, SignalStrength.MEDIUM, "Detected success-claim phrasing"),
)

OPPORTUNITY_PATTERNS: tuple[LexicalPattern, ...] = (
    LexicalPattern("申报通知", "opportunity.application_language", SignalCategory.OPPORTUNITY, SignalStrength.STRONG, "Detected application-language phrasing"),
    LexicalPattern("征集通知", "opportunity.application_language", SignalCategory.OPPORTUNITY, SignalStrength.STRONG, "Detected application-language phrasing"),
    LexicalPattern("项目申报", "opportunity.application_language", SignalCategory.OPPORTUNITY, SignalStrength.MEDIUM, "Detected application-language phrasing"),
    LexicalPattern("申报工作", "opportunity.application_language", SignalCategory.OPPORTUNITY, SignalStrength.MEDIUM, "Detected application-language phrasing"),
    LexicalPattern("申报截止", "opportunity.deadline_language", SignalCategory.OPPORTUNITY, SignalStrength.STRONG, "Detected explicit deadline expression"),
    LexicalPattern("报名截止", "opportunity.deadline_language", SignalCategory.OPPORTUNITY, SignalStrength.STRONG, "Detected explicit deadline expression"),
    LexicalPattern("申报时间", "opportunity.deadline_language", SignalCategory.OPPORTUNITY, SignalStrength.MEDIUM, "Detected deadline-related language"),
    LexicalPattern("报名时间", "opportunity.deadline_language", SignalCategory.OPPORTUNITY, SignalStrength.MEDIUM, "Detected deadline-related language"),
    LexicalPattern("申报条件", "opportunity.eligibility_language", SignalCategory.OPPORTUNITY, SignalStrength.STRONG, "Detected eligibility language"),
    LexicalPattern("申请条件", "opportunity.eligibility_language", SignalCategory.OPPORTUNITY, SignalStrength.STRONG, "Detected eligibility language"),
    LexicalPattern("报名条件", "opportunity.eligibility_language", SignalCategory.OPPORTUNITY, SignalStrength.STRONG, "Detected eligibility language"),
    LexicalPattern("支持对象", "opportunity.eligibility_language", SignalCategory.OPPORTUNITY, SignalStrength.MEDIUM, "Detected eligibility language"),
    LexicalPattern("征集对象", "opportunity.eligibility_language", SignalCategory.OPPORTUNITY, SignalStrength.MEDIUM, "Detected eligibility language"),
    LexicalPattern("支持范围", "opportunity.eligibility_language", SignalCategory.OPPORTUNITY, SignalStrength.MEDIUM, "Detected eligibility language"),
)

ALL_LEXICAL_PATTERNS: tuple[LexicalPattern, ...] = (
    *MARKETING_PATTERNS,
    *INTERMEDIARY_PATTERNS,
    *OPPORTUNITY_PATTERNS,
)


def _iter_matches(text: str, phrase: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        index = text.find(phrase, start)
        if index < 0:
            break
        end = index + len(phrase)
        spans.append((index, end))
        start = end
    return spans


def _apply_patterns(text: str, collector: RuleCollector, *, field_prefix: str) -> None:
    for pattern in ALL_LEXICAL_PATTERNS:
        for start, end in _iter_matches(text, pattern.phrase):
            evidence_id = collector.add_text_evidence(
                text,
                start,
                end,
                field=f"{field_prefix}.{pattern.code}",
            )
            collector.add_signal(
                code=pattern.code,
                category=pattern.category,
                strength=pattern.strength,
                description=pattern.description,
                evidence_id=evidence_id,
            )


def _apply_entity_candidates(text: str, collector: RuleCollector) -> None:
    seen = {item.text for item in collector.entity_candidates}
    for suffix in _ORG_SUFFIXES:
        start = 0
        while True:
            if len(seen) >= 5:
                return
            index = text.find(suffix, start)
            if index < 0:
                break
            left = index
            while left > 0 and "\u4e00" <= text[left - 1] <= "\u9fff":
                left -= 1
                if index - left >= 12:
                    break
            name = text[left : index + len(suffix)]
            end = index + len(suffix)
            start = end
            if not (4 <= len(name) <= 32) or name in seen:
                continue
            seen.add(name)
            evidence_id = collector.add_text_evidence(
                text,
                left,
                end,
                field="entity.organization",
            )
            collector.entity_candidates.append(
                EntityCandidate(text=name, kind="organization", evidence_id=evidence_id)
            )


def apply_lexical_rules(payload: ContentIntelligenceInput, collector: RuleCollector) -> None:
    if payload.title:
        _apply_patterns(payload.title, collector, field_prefix="title")
        _apply_entity_candidates(payload.title, collector)
    _apply_patterns(payload.normalized_text, collector, field_prefix="body")
    _apply_entity_candidates(payload.normalized_text, collector)
