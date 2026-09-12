"""LLM provider interface. Providers emit structured JSON, not business judgments."""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.integrations.llm.schemas import LLMStructuredResponse


class LLMProvider(ABC):
    @abstractmethod
    def structured_generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> LLMStructuredResponse:
        """Return a JSON object matching response_model. Does not validate business rules."""
