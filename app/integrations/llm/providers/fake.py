"""Deterministic stub provider. Never performs network I/O."""

from pydantic import BaseModel

from app.integrations.llm.base import LLMProvider
from app.integrations.llm.errors import LLMProviderError
from app.integrations.llm.schemas import LLMStructuredResponse, LLMUsage

_DEFAULT_USAGE = LLMUsage(
    input_tokens=1000,
    output_tokens=300,
    total_tokens=1300,
    estimated_cost=None,
    currency=None,
)


class FakeLLMProvider(LLMProvider):
    def __init__(
        self,
        responses: list[dict | BaseModel | Exception] | dict | BaseModel | Exception | None = None,
        *,
        usage: LLMUsage | None = None,
        model: str = "fake-model",
        latency_ms: int = 12,
        request_id: str = "fake-req-1",
    ) -> None:
        if responses is None:
            script: list[dict | BaseModel | Exception] = []
        elif isinstance(responses, list):
            script = list(responses)
        else:
            script = [responses]
        self._script = script
        self._index = 0
        self.usage = usage or _DEFAULT_USAGE
        self.model = model
        self.latency_ms = latency_ms
        self.request_id = request_id
        self.calls: list[dict[str, str]] = []

    def structured_generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> LLMStructuredResponse:
        del response_model
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        if not self._script:
            raise LLMProviderError("FakeLLMProvider has no scripted response")
        if self._index < len(self._script):
            item = self._script[self._index]
            self._index += 1
        else:
            item = self._script[-1]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, BaseModel):
            data = item.model_dump(mode="json")
        else:
            data = item
        return LLMStructuredResponse(
            data=data,
            usage=self.usage,
            provider="fake",
            model=self.model,
            request_id=self.request_id,
            latency_ms=self.latency_ms,
        )
