"""Opportunity domain enumerations.

Stored as strings in the database so SQLite and PostgreSQL stay compatible.
"""

from enum import StrEnum


class OpportunityType(StrEnum):
    POLICY = "policy"
    COMPETITION = "competition"
    FINANCIAL_SERVICE = "financial_service"
    EQUITY_FUNDING = "equity_funding"
    PARK_SERVICE = "park_service"
    SCENARIO = "scenario"
    OTHER = "other"


class OpportunityStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    UPCOMING = "upcoming"
    EXPIRED = "expired"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class SourceType(StrEnum):
    OFFICIAL_DOCUMENT = "official_document"
    OFFICIAL_NEWS = "official_news"
    OFFICIAL_WECHAT = "official_wechat"
    MEDIA_ARTICLE = "media_article"
    WECHAT_ARTICLE = "wechat_article"
    SERVICE_PROVIDER = "service_provider"
    OTHER = "other"
    UNKNOWN = "unknown"


class RequirementOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    GTE = "gte"
    LTE = "lte"
    GT = "gt"
    LT = "lt"
    CONTAINS = "contains"
    EXISTS = "exists"
    MANUAL_REVIEW = "manual_review"
