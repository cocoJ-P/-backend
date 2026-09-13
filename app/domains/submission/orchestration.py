"""UserSubmission processing pipeline.

Reuses Content Ingestion and Opportunity Intelligence services.
Does not HTTP-call this application and does not create Opportunity records.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.identity.schemas import CurrentIdentity
from app.domains.intelligence.service import analyze_source
from app.domains.submission.enums import SubmissionFailureStage, SubmissionStatus
from app.domains.submission.models import UserSubmission
from app.domains.submission.repository import save_submission
from app.domains.submission.schemas import UserSubmissionDetail
from app.domains.submission.service import (
    build_submission_detail,
    require_enterprise_submission,
)
from app.integrations.content.schemas import IngestRequest, InputType
from app.integrations.content.service import ingest

logger = get_logger(__name__)

ERROR_MESSAGE_MAX_CHARS = 500
PROCESSING_STATUSES = {
    SubmissionStatus.INGESTING.value,
    SubmissionStatus.ANALYZING.value,
}


class SubmissionOrchestrator:
    def __init__(self, db: Session) -> None:
        self.db = db

    def process(self, submission_id: UUID, identity: CurrentIdentity) -> UserSubmissionDetail:
        submission = require_enterprise_submission(self.db, identity.enterprise_id, submission_id)
        if submission.status in PROCESSING_STATUSES:
            raise AppException(
                "SUBMISSION_ALREADY_PROCESSING",
                "Submission is already being processed",
                status_code=409,
                details={
                    "submission_id": str(submission.id),
                    "status": submission.status,
                },
            )
        if submission.status == SubmissionStatus.SUCCEEDED.value:
            logger.info(
                "submission process idempotent submission_id=%s user_id=%s enterprise_id=%s",
                submission.id,
                identity.user_id,
                identity.enterprise_id,
            )
            return build_submission_detail(self.db, submission)

        skip_ingest = self._can_reuse_ingestion(submission)
        if not skip_ingest:
            self._run_ingest(submission)
        else:
            logger.info(
                "submission retry skips ingest submission_id=%s source_id=%s ingestion_id=%s",
                submission.id,
                submission.source_id,
                submission.ingestion_id,
            )
            self._transition(submission, SubmissionStatus.ANALYZING)

        self._run_analyze(submission)
        return build_submission_detail(self.db, submission)

    def _can_reuse_ingestion(self, submission: UserSubmission) -> bool:
        return (
            submission.status == SubmissionStatus.FAILED.value
            and submission.failure_stage == SubmissionFailureStage.ANALYZE.value
            and submission.source_id is not None
            and submission.ingestion_id is not None
        )

    def _run_ingest(self, submission: UserSubmission) -> None:
        self._transition(submission, SubmissionStatus.INGESTING)
        try:
            result = ingest(
                self.db,
                IngestRequest(
                    content_type=InputType(submission.input_type),
                    content=submission.input_content,
                ),
            )
        except AppException as exc:
            self._mark_failed(submission, SubmissionFailureStage.INGEST, exc)
            raise self._with_submission_context(
                exc,
                submission.id,
                SubmissionFailureStage.INGEST,
            ) from exc
        except Exception as exc:
            wrapped = AppException(
                "SUBMISSION_PROCESSING_FAILED",
                "Submission ingestion failed",
                status_code=500,
            )
            self._mark_failed(submission, SubmissionFailureStage.INGEST, wrapped)
            raise self._with_submission_context(
                wrapped,
                submission.id,
                SubmissionFailureStage.INGEST,
            ) from exc

        submission.source_id = result.source.id
        submission.ingestion_id = result.ingestion.id
        self._transition(submission, SubmissionStatus.ANALYZING)

    def _run_analyze(self, submission: UserSubmission) -> None:
        if submission.source_id is None or submission.ingestion_id is None:
            raise AppException(
                "SUBMISSION_STATE_INVALID",
                "Submission is missing ingestion context",
                status_code=409,
                details={
                    "submission_id": str(submission.id),
                    "failure_stage": SubmissionFailureStage.ANALYZE.value,
                },
            )
        if submission.status != SubmissionStatus.ANALYZING.value:
            self._transition(submission, SubmissionStatus.ANALYZING)
        try:
            execution = analyze_source(
                self.db,
                submission.source_id,
                ingestion_id=submission.ingestion_id,
                force=False,
            )
        except AppException as exc:
            run_id = _reliable_run_id(exc)
            self._mark_failed(
                submission,
                SubmissionFailureStage.ANALYZE,
                exc,
                intelligence_run_id=run_id,
            )
            raise self._with_submission_context(
                exc,
                submission.id,
                SubmissionFailureStage.ANALYZE,
            ) from exc
        except Exception as exc:
            wrapped = AppException(
                "SUBMISSION_PROCESSING_FAILED",
                "Submission analysis failed",
                status_code=500,
            )
            self._mark_failed(submission, SubmissionFailureStage.ANALYZE, wrapped)
            raise self._with_submission_context(
                wrapped,
                submission.id,
                SubmissionFailureStage.ANALYZE,
            ) from exc

        submission.intelligence_run_id = execution.run.id
        submission.status = SubmissionStatus.SUCCEEDED.value
        submission.failure_stage = None
        submission.error_code = None
        submission.error_message = None
        submission.completed_at = utc_now()
        self._persist(submission)
        logger.info(
            "submission succeeded submission_id=%s user_id=%s enterprise_id=%s "
            "source_id=%s ingestion_id=%s intelligence_run_id=%s",
            submission.id,
            submission.user_id,
            submission.enterprise_id,
            submission.source_id,
            submission.ingestion_id,
            submission.intelligence_run_id,
        )

    def _transition(self, submission: UserSubmission, status: SubmissionStatus) -> None:
        previous = submission.status
        submission.status = status.value
        submission.failure_stage = None
        submission.error_code = None
        submission.error_message = None
        submission.completed_at = None
        self._persist(submission)
        logger.info(
            "submission status transition submission_id=%s user_id=%s enterprise_id=%s from=%s to=%s",
            submission.id,
            submission.user_id,
            submission.enterprise_id,
            previous,
            status.value,
        )

    def _mark_failed(
        self,
        submission: UserSubmission,
        stage: SubmissionFailureStage,
        exc: AppException,
        *,
        intelligence_run_id: UUID | None = None,
    ) -> None:
        submission.status = SubmissionStatus.FAILED.value
        submission.failure_stage = stage.value
        submission.error_code = exc.code
        submission.error_message = _safe_error_message(exc.message)
        submission.completed_at = utc_now()
        if intelligence_run_id is not None:
            submission.intelligence_run_id = intelligence_run_id
        self._persist(submission)
        logger.info(
            "submission failed submission_id=%s user_id=%s enterprise_id=%s "
            "failure_stage=%s error_code=%s",
            submission.id,
            submission.user_id,
            submission.enterprise_id,
            stage.value,
            exc.code,
        )

    def _persist(self, submission: UserSubmission) -> None:
        save_submission(self.db, submission)

    def _with_submission_context(
        self,
        exc: AppException,
        submission_id: UUID,
        stage: SubmissionFailureStage,
    ) -> AppException:
        details = _merge_details(exc.details, submission_id, stage)
        return AppException(
            exc.code,
            exc.message,
            status_code=exc.status_code,
            details=details,
        )


def _merge_details(
    details: object | None,
    submission_id: UUID,
    stage: SubmissionFailureStage,
) -> dict:
    if details is None:
        merged: dict = {}
    elif isinstance(details, dict):
        merged = dict(details)
    else:
        merged = {"original": details}
    merged["submission_id"] = str(submission_id)
    merged["failure_stage"] = stage.value
    return merged


def _reliable_run_id(exc: AppException) -> UUID | None:
    if not isinstance(exc.details, dict):
        return None
    raw = exc.details.get("run_id")
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _safe_error_message(message: str) -> str | None:
    text = (message or "").strip()
    if not text:
        return None
    if "Traceback (most recent call last)" in text:
        text = text.split("Traceback (most recent call last)", 1)[0].strip()
    secret = (settings.LLM_API_KEY or "").strip()
    if secret:
        text = text.replace(secret, "[redacted]")
    text = text.replace("Authorization", "[redacted]")
    text = text[:ERROR_MESSAGE_MAX_CHARS]
    return text or None
