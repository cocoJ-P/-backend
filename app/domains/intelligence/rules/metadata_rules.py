"""Metadata presence signals. Existence is not authenticity."""

from app.domains.intelligence.enums import EvidenceKind, SignalCategory, SignalStrength
from app.domains.intelligence.rules.collector import RuleCollector
from app.domains.intelligence.schemas import ContentIntelligenceInput


def apply_metadata_rules(payload: ContentIntelligenceInput, collector: RuleCollector) -> None:
    if payload.publisher and payload.publisher.strip():
        evidence_id = collector.add_literal_evidence(
            payload.publisher.strip(),
            field="metadata.publisher_present",
            kind=EvidenceKind.METADATA,
        )
        collector.add_signal(
            code="metadata.publisher_present",
            category=SignalCategory.METADATA,
            strength=SignalStrength.MEDIUM,
            description="Publisher metadata is present",
            evidence_id=evidence_id,
        )

    if payload.published_at is not None:
        evidence_id = collector.add_literal_evidence(
            payload.published_at.isoformat(),
            field="metadata.published_at_present",
            kind=EvidenceKind.METADATA,
        )
        collector.add_signal(
            code="metadata.published_at_present",
            category=SignalCategory.METADATA,
            strength=SignalStrength.MEDIUM,
            description="published_at metadata is present",
            evidence_id=evidence_id,
        )
