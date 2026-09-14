"""Feishu integration enumerations."""

from enum import StrEnum


class FeishuErrorCode(StrEnum):
    NOT_CONFIGURED = "FEISHU_NOT_CONFIGURED"
    AUTH_FAILED = "FEISHU_AUTH_FAILED"
    REQUEST_FAILED = "FEISHU_REQUEST_FAILED"
    RATE_LIMITED = "FEISHU_RATE_LIMITED"
    TIMEOUT = "FEISHU_TIMEOUT"
    NETWORK_ERROR = "FEISHU_NETWORK_ERROR"
    INVALID_RESPONSE = "FEISHU_INVALID_RESPONSE"


class FeishuBindingSyncStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
