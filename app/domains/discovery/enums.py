"""Discovery enumerations. Stored as strings in the database."""

from enum import StrEnum


class DiscoveryStatus(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class DiscoveryPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class DiscoveryReferenceType(StrEnum):
    OPPORTUNITY = "opportunity"
    SOURCE = "source"
    MANUAL = "manual"


class DiscoveryDisposition(StrEnum):
    SAVED = "saved"
    DEPRIORITIZED = "deprioritized"
