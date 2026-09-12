"""Opportunity Intelligence domain.

B4.1 defines the contract. B4.2 adds a deterministic Rule Layer.
B4.3 adds LLM structured extraction of claims.
B4.4 orchestrates the pipeline and persists IntelligenceRun records.
"""

from app.domains.intelligence.contracts import (
    DEFAULT_ANALYZER_VERSION,
    SCHEMA_VERSION,
)
from app.domains.intelligence.schemas import (
    ContentIntelligenceInput,
    ContentIntelligenceResult,
    IntelligenceAnalysis,
    IntelligenceEvidence,
    IntelligenceMetadata,
    OpportunityClaim,
    SourceAssessment,
)

__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_ANALYZER_VERSION",
    "ContentIntelligenceInput",
    "ContentIntelligenceResult",
    "IntelligenceAnalysis",
    "IntelligenceEvidence",
    "IntelligenceMetadata",
    "OpportunityClaim",
    "SourceAssessment",
]
