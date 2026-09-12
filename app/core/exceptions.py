"""Lightweight application exceptions.

FastAPI / Pydantic request validation (HTTP 422) keeps native behavior.
Only AppException subclasses are mapped to the unified error envelope.
"""


class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: object | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundException(AppException):
    def __init__(
        self,
        message: str = "Resource not found",
        *,
        code: str = "NOT_FOUND",
        details: object | None = None,
    ) -> None:
        super().__init__(code, message, status_code=404, details=details)


class ValidationException(AppException):
    def __init__(
        self,
        message: str = "Validation failed",
        *,
        details: object | None = None,
    ) -> None:
        super().__init__("VALIDATION_ERROR", message, status_code=400, details=details)


class ConflictException(AppException):
    def __init__(
        self,
        message: str = "Resource conflict",
        *,
        details: object | None = None,
    ) -> None:
        super().__init__("CONFLICT", message, status_code=409, details=details)


class ExternalServiceException(AppException):
    def __init__(
        self,
        message: str = "External service error",
        *,
        details: object | None = None,
    ) -> None:
        super().__init__(
            "EXTERNAL_SERVICE_ERROR",
            message,
            status_code=502,
            details=details,
        )
