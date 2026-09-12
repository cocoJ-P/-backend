"""Provider-agnostic LLM DTOs. No Opportunity / Intelligence business types."""

from typing import Any

from pydantic import BaseModel, Field


class LLMUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    currency: str | None = None


class LLMStructuredResponse(BaseModel):
    data: dict[str, Any]
    usage: LLMUsage = Field(default_factory=LLMUsage)
    provider: str
    model: str
    request_id: str | None = None
    latency_ms: int = 0
