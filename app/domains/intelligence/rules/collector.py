"""Mutable collector used while running deterministic rules."""

from app.domains.intelligence.enums import EvidenceKind, SignalCategory, SignalStrength
from app.domains.intelligence.rules.evidence import excerpt_around, make_evidence
from app.domains.intelligence.rules.schemas import MAX_EVIDENCE_PER_SIGNAL, RuleSignal
from app.domains.intelligence.schemas import IntelligenceEvidence


class RuleCollector:
    def __init__(self) -> None:
        self.evidence: list[IntelligenceEvidence] = []
        self.signals: dict[str, RuleSignal] = {}
        self.date_candidates: list[DateCandidate] = []
        self.url_candidates: list[URLCandidate] = []
        self.amount_candidates: list[AmountCandidate] = []
        self.entity_candidates: list[EntityCandidate] = []
        self._seq = 0

    def next_id(self) -> str:
        self._seq += 1
        return f"rule_ev_{self._seq:03d}"

    def add_text_evidence(
        self,
        text: str,
        start: int,
        end: int,
        *,
        field: str,
        kind: EvidenceKind = EvidenceKind.DIRECT_QUOTE,
        source: str = "rule_layer",
    ) -> str:
        evidence_id = self.next_id()
        snippet = excerpt_around(text, start, end)
        self.evidence.append(
            make_evidence(
                evidence_id=evidence_id,
                text=snippet,
                field=field,
                kind=kind,
                source=source,
            )
        )
        return evidence_id

    def add_literal_evidence(
        self,
        text: str,
        *,
        field: str,
        kind: EvidenceKind,
        source: str = "rule_layer",
    ) -> str:
        evidence_id = self.next_id()
        self.evidence.append(
            make_evidence(
                evidence_id=evidence_id,
                text=text,
                field=field,
                kind=kind,
                source=source,
            )
        )
        return evidence_id

    def add_signal(
        self,
        *,
        code: str,
        category: SignalCategory,
        strength: SignalStrength,
        description: str,
        evidence_id: str,
    ) -> None:
        existing = self.signals.get(code)
        if existing is None:
            self.signals[code] = RuleSignal(
                code=code,
                category=category,
                strength=strength,
                description=description,
                occurrence_count=1,
                evidence_ids=[evidence_id],
            )
            return
        existing.occurrence_count += 1
        if (
            evidence_id not in existing.evidence_ids
            and len(existing.evidence_ids) < MAX_EVIDENCE_PER_SIGNAL
        ):
            existing.evidence_ids.append(evidence_id)
        rank = {SignalStrength.WEAK: 1, SignalStrength.MEDIUM: 2, SignalStrength.STRONG: 3}
        if rank[strength] > rank[existing.strength]:
            existing.strength = strength
            existing.description = description
