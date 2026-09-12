"""B4.3 extraction envelope. Provider metadata stays outside ContentIntelligenceResult."""

from app.domains.intelligence.schemas import ContentIntelligenceResult
from app.integrations.llm.schemas import LLMUsage
from pydantic import BaseModel


class LLMExtractionResult(BaseModel):
    intelligence_result: ContentIntelligenceResult
    usage: LLMUsage
    provider: str
    model: str
    prompt_version: str
    request_id: str | None = None
    latency_ms: int | None = None
