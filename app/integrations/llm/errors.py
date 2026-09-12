"""LLM integration errors. Domain code should not catch vendor SDK exceptions."""


class LLMProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        details: object | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.details = details


class LLMTimeoutError(LLMProviderError):
    def __init__(self, message: str = "LLM request timed out", *, details: object | None = None) -> None:
        super().__init__(message, retryable=True, details=details)


class LLMRateLimitError(LLMProviderError):
    def __init__(self, message: str = "LLM rate limit exceeded", *, details: object | None = None) -> None:
        super().__init__(message, retryable=True, details=details)


class LLMStructuredOutputError(LLMProviderError):
    def __init__(
        self,
        message: str = "LLM structured output was missing or malformed",
        *,
        details: object | None = None,
    ) -> None:
        super().__init__(message, retryable=True, details=details)


class LLMSchemaValidationError(LLMProviderError):
    def __init__(
        self,
        message: str = "LLM output failed schema or evidence validation",
        *,
        details: object | None = None,
    ) -> None:
        super().__init__(message, retryable=False, details=details)
