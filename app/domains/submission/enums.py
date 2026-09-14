"""UserSubmission enumerations. Stored as strings in the database."""

from enum import StrEnum


class SubmissionInputType(StrEnum):
    URL = "url"
    TEXT = "text"


class SubmissionStatus(StrEnum):
    PENDING = "pending"
    INGESTING = "ingesting"
    ANALYZING = "analyzing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SubmissionFailureStage(StrEnum):
    INGEST = "ingest"
    ANALYZE = "analyze"


class SubmissionOriginType(StrEnum):
    USER_INPUT = "user_input"
    DISCOVERY = "discovery"
