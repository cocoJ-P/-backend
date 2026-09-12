"""Create an LLMProvider from Settings. Domain code must not instantiate SDKs."""

from app.core.config import settings
from app.integrations.llm.base import LLMProvider
from app.integrations.llm.errors import LLMProviderError
from app.integrations.llm.providers.fake import FakeLLMProvider
from app.integrations.llm.providers.openai_compatible import OpenAICompatibleProvider


def create_llm_provider() -> LLMProvider:
    name = (settings.LLM_PROVIDER or "").strip().lower()
    if name in {"fake", "stub"}:
        return FakeLLMProvider()
    if name in {"openai", "openai_compatible"}:
        return OpenAICompatibleProvider(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL or None,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )
    raise LLMProviderError(f"unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")
