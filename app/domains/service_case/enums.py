"""ServiceCase enumerations. Stored as strings in the database."""

from enum import StrEnum


class ServiceCaseStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"
