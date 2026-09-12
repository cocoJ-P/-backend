"""Opportunity Intelligence enumerations.

These describe content-layer judgments and claims, not verified facts.
"""

from enum import StrEnum


class ContentNature(StrEnum):
    OPPORTUNITY_ANNOUNCEMENT = "opportunity_announcement"
    OPPORTUNITY_INTERPRETATION = "opportunity_interpretation"
    NEWS_REPORT = "news_report"
    MARKETING_CONTENT = "marketing_content"
    SERVICE_CONTENT = "service_content"
    GENERAL_INFORMATION = "general_information"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class OpportunityRelevance(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"
    UNKNOWN = "unknown"


class ApparentSourceType(StrEnum):
    OFFICIAL_LIKE = "official_like"
    MEDIA_LIKE = "media_like"
    SERVICE_PROVIDER_LIKE = "service_provider_like"
    INDIVIDUAL_LIKE = "individual_like"
    UNKNOWN = "unknown"


class MarketingLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class IntermediaryLevel(StrEnum):
    NONE = "none"
    POSSIBLE = "possible"
    LIKELY = "likely"
    UNKNOWN = "unknown"


class OriginalityClaim(StrEnum):
    CLAIMS_ORIGINAL = "claims_original"
    APPEARS_REPOST = "appears_repost"
    APPEARS_INTERPRETATION = "appears_interpretation"
    UNCLEAR = "unclear"


class ClaimedStatus(StrEnum):
    ACTIVE = "active"
    UPCOMING = "upcoming"
    EXPIRED = "expired"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class EvidenceKind(StrEnum):
    DIRECT_QUOTE = "direct_quote"
    METADATA = "metadata"
    DERIVED_SIGNAL = "derived_signal"


class SignalCategory(StrEnum):
    MARKETING = "marketing"
    INTERMEDIARY = "intermediary"
    OPPORTUNITY = "opportunity"
    METADATA = "metadata"
    STRUCTURE = "structure"
    DATE = "date"
    URL = "url"
    AMOUNT = "amount"
    OTHER = "other"


class SignalStrength(StrEnum):
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"


class DateCandidateKind(StrEnum):
    PUBLISH_DATE = "publish_date"
    DEADLINE = "deadline"
    START_DATE = "start_date"
    END_DATE = "end_date"
    EVENT_DATE = "event_date"
    UNKNOWN = "unknown"


class URLCandidateKind(StrEnum):
    SAME_PAGE = "same_page"
    EXTERNAL_LINK = "external_link"
    OFFICIAL_DOMAIN_LIKE = "official_domain_like"
    DOCUMENT_LINK = "document_link"
    UNKNOWN = "unknown"


class AmountKind(StrEnum):
    FUNDING = "funding"
    SUBSIDY = "subsidy"
    LOAN = "loan"
    FINANCING = "financing"
    AWARD = "award"
    UNKNOWN = "unknown"


class IntelligenceRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
