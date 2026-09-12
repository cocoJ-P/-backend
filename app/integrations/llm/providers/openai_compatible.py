"""OpenAI-compatible chat completions provider.

Knows how to call an OpenAI-style API. Does not know Opportunity or Intelligence types.
"""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel

from app.integrations.llm.base import LLMProvider
from app.integrations.llm.errors import (
    LLMProviderError,
    LLMRateLimitError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.integrations.llm.schemas import LLMStructuredResponse, LLMUsage


def _usage_from_completion(completion: Any) -> LLMUsage:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return LLMUsage()
    input_tokens = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost=None,
        currency=None,
    )


def _dump_parsed(parsed: Any) -> dict[str, Any]:
    if parsed is None:
        raise LLMStructuredOutputError("structured parse returned no object")
    if isinstance(parsed, BaseModel):
        return parsed.model_dump(mode="json")
    if isinstance(parsed, dict):
        return parsed
    raise LLMStructuredOutputError("structured parse returned an unsupported type")


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 60,
        max_retries: int = 2,
    ) -> None:
        if not api_key.strip():
            raise LLMProviderError("LLM_API_KEY is not configured")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.strip() if base_url else None
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            kwargs: dict[str, Any] = {
                "api_key": self._api_key,
                "timeout": self._timeout_seconds,
                "max_retries": 0,
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def structured_generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> LLMStructuredResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        last_error: LLMProviderError | None = None
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                completion = self._call(messages, response_model)
                data = self._extract_data(completion)
                latency_ms = int((time.perf_counter() - started) * 1000)
                return LLMStructuredResponse(
                    data=data,
                    usage=_usage_from_completion(completion),
                    provider="openai",
                    model=self._model,
                    request_id=getattr(completion, "id", None),
                    latency_ms=latency_ms,
                )
            except LLMProviderError as exc:
                last_error = exc
                if not exc.retryable or attempt >= attempts - 1:
                    raise
                time.sleep(min(0.2 * (2**attempt), 2.0))
        assert last_error is not None
        raise last_error

    def _call(self, messages: list[dict[str, str]], response_model: type[BaseModel]) -> Any:
        client = self._get_client()
        try:
            parse_fn = getattr(client.chat.completions, "parse", None)
            if parse_fn is None:
                parse_fn = getattr(getattr(client, "beta").chat.completions, "parse", None)
            if parse_fn is not None:
                return parse_fn(
                    model=self._model,
                    messages=messages,
                    response_format=response_model,
                    temperature=0,
                )
            return client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": response_model.model_json_schema(),
                        "strict": False,
                    },
                },
            )
        except Exception as exc:
            raise self._map_exception(exc) from exc

    def _extract_data(self, completion: Any) -> dict[str, Any]:
        try:
            choice = completion.choices[0]
            message = choice.message
        except (IndexError, AttributeError) as exc:
            raise LLMStructuredOutputError("LLM response contained no choices") from exc
        if getattr(message, "refusal", None):
            raise LLMStructuredOutputError(
                "LLM refused to produce structured output",
                details={"refusal": message.refusal},
            )
        parsed = getattr(message, "parsed", None)
        if parsed is not None:
            return _dump_parsed(parsed)
        content = getattr(message, "content", None)
        if not content or not isinstance(content, str):
            raise LLMStructuredOutputError("LLM response content was empty")
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMStructuredOutputError("LLM response was not valid JSON") from exc
        if not isinstance(raw, dict):
            raise LLMStructuredOutputError("LLM JSON root must be an object")
        return raw

    def _map_exception(self, exc: Exception) -> LLMProviderError:
        try:
            from openai import APIStatusError, APITimeoutError, RateLimitError
        except ImportError:
            return LLMProviderError(str(exc), details={"type": type(exc).__name__})

        if isinstance(exc, APITimeoutError):
            return LLMTimeoutError(str(exc) or "LLM request timed out")
        if isinstance(exc, RateLimitError):
            return LLMRateLimitError(str(exc) or "LLM rate limit exceeded")
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            retryable = status is not None and int(status) >= 500
            if status == 429:
                return LLMRateLimitError(str(exc) or "LLM rate limit exceeded")
            return LLMProviderError(
                str(exc) or "LLM provider error",
                retryable=retryable,
                details={"status_code": status},
            )
        name = type(exc).__name__.lower()
        if "timeout" in name:
            return LLMTimeoutError(str(exc) or "LLM request timed out")
        return LLMProviderError(str(exc), details={"type": type(exc).__name__})
