"""Feishu integration errors. Never include secrets in messages or repr."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.integrations.feishu.enums import FeishuErrorCode

RETRYABLE_CODES = {
    FeishuErrorCode.RATE_LIMITED,
    FeishuErrorCode.TIMEOUT,
    FeishuErrorCode.NETWORK_ERROR,
}

AMBIGUOUS_CREATE_CODES = {
    FeishuErrorCode.TIMEOUT,
    FeishuErrorCode.NETWORK_ERROR,
}

AUTH_PROVIDER_CODES = {10003, 10010, 10012, 10013, 10014, 99991661, 99991663, 99991664}
RATE_LIMIT_PROVIDER_CODES = {99991400, 99991401, 99991402}
BITABLE_RECORD_NOT_FOUND_PROVIDER_CODES = {1254043, 1254044}

ERROR_MESSAGE_MAX_CHARS = 500

_BEARER_PATTERN = re.compile(r"(?i)bearer\s+\S+")
_TENANT_TOKEN_ASSIGN_PATTERN = re.compile(r"(?i)tenant_access_token[=:\s]+\S+")


def sanitize_feishu_text(text: str, secrets: Sequence[str] = ()) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    if "Traceback (most recent call last)" in value:
        value = value.split("Traceback (most recent call last)", 1)[0].strip()
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[redacted]")
    value = _BEARER_PATTERN.sub("Bearer [redacted]", value)
    value = _TENANT_TOKEN_ASSIGN_PATTERN.sub("tenant_access_token=[redacted]", value)
    value = value.replace("Authorization", "[redacted]")
    value = value.replace("tenant_access_token", "[redacted]")
    value = value.replace("app_secret", "[redacted]")
    return value[:ERROR_MESSAGE_MAX_CHARS]


class FeishuIntegrationError(Exception):
    def __init__(
        self,
        code: FeishuErrorCode | str,
        message: str,
        *,
        retryable: bool | None = None,
        provider_code: object | None = None,
        log_id: str | None = None,
        secrets: Sequence[str] = (),
    ) -> None:
        self.code = FeishuErrorCode(code)
        self.message = sanitize_feishu_text(message, secrets) or self.code.value
        self.retryable = bool(self.code in RETRYABLE_CODES if retryable is None else retryable)
        self.provider_code = provider_code
        self.log_id = log_id
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        return (
            "FeishuIntegrationError("
            f"code={self.code.value!r}, retryable={self.retryable}, "
            f"provider_code={self.provider_code!r})"
        )


def format_safe_feishu_error(error: FeishuIntegrationError) -> str:
    """CLI/log diagnostic. Never includes secrets, tokens, or raw bodies."""
    lines = [f"Error: {error.code}"]
    if error.provider_code is not None and error.provider_code != "":
        lines.append(f"Provider code: {error.provider_code}")
    if error.log_id:
        lines.append(f"Log id: {error.log_id}")
    message = (error.message or "").strip()
    if message:
        lines.append(f"Provider message: {message}")
    return "\n".join(lines)


def is_ambiguous_create_error(error: FeishuIntegrationError) -> bool:
    return error.code in AMBIGUOUS_CREATE_CODES


def is_retryable_error_code(code: object) -> bool:
    value = getattr(code, "value", code)
    try:
        return FeishuErrorCode(str(value)) in RETRYABLE_CODES
    except ValueError:
        return False


def is_bitable_record_not_found(error: FeishuIntegrationError) -> bool:
    if error.code == FeishuErrorCode.RECORD_NOT_FOUND:
        return True
    if error.provider_code in BITABLE_RECORD_NOT_FOUND_PROVIDER_CODES:
        return True
    if error.provider_code == 404:
        return True
    message = (error.message or "").lower()
    return "record not found" in message or "record_id not found" in message
