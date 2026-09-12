"""Deterministic Rule Layer entrypoint. Outputs signals, not IntelligenceResult."""

from app.core.time import utc_now
from app.domains.intelligence.rules.amount_rules import apply_amount_rules
from app.domains.intelligence.rules.collector import RuleCollector
from app.domains.intelligence.rules.date_rules import apply_date_rules
from app.domains.intelligence.rules.lexical_rules import apply_lexical_rules
from app.domains.intelligence.rules.metadata_rules import apply_metadata_rules
from app.domains.intelligence.rules.schemas import (
    RULE_VERSION,
    RuleAnalysisMetadata,
    RuleAnalysisResult,
)
from app.domains.intelligence.rules.structural_rules import apply_structural_rules
from app.domains.intelligence.rules.url_rules import apply_url_rules
from app.domains.intelligence.schemas import ContentIntelligenceInput


class RuleAnalyzer:
    """Read-only analyzer. Does not mutate normalized text or B3 metadata."""

    def analyze(self, payload: ContentIntelligenceInput) -> RuleAnalysisResult:
        collector = RuleCollector()
        apply_metadata_rules(payload, collector)
        apply_lexical_rules(payload, collector)
        apply_structural_rules(payload, collector)
        apply_date_rules(payload, collector)
        apply_url_rules(payload, collector)
        apply_amount_rules(payload, collector)
        return RuleAnalysisResult(
            signals=list(collector.signals.values()),
            date_candidates=collector.date_candidates,
            url_candidates=collector.url_candidates,
            amount_candidates=collector.amount_candidates,
            entity_candidates=collector.entity_candidates,
            evidence=collector.evidence,
            metadata=RuleAnalysisMetadata(rule_version=RULE_VERSION, created_at=utc_now()),
        )
