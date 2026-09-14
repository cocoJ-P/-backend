"""Create, validate, scope, and assemble UserSubmission responses."""

from __future__ import annotations

import re
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException, NotFoundException
from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.enterprise.repository import get_enterprise
from app.domains.identity.models import User
from app.domains.identity.repository import get_user_by_id
from app.domains.identity.schemas import CurrentIdentity, MeEnterprise, MeUser
from app.domains.intelligence.models import IntelligenceRun
from app.domains.intelligence.orchestration import load_intelligence_result
from app.domains.intelligence.schemas import ContentIntelligenceResult
from app.domains.submission.enums import SubmissionInputType, SubmissionOriginType, SubmissionStatus
from app.domains.submission.models import UserSubmission
from app.domains.submission.repository import (
    create_submission,
    get_submission_for_enterprise,
    list_submissions_for_enterprise,
    list_submissions_for_user,
)
from app.domains.submission.schemas import (
    CreateUserSubmissionRequest,
    SubmissionContentSummary,
    SubmissionIntelligenceSummary,
    SubmissionRecord,
    UserActor,
    UserSubmissionCreateResponse,
    UserSubmissionDetail,
    UserSubmissionListResponse,
    UserSubmissionSummary,
)
from app.domains.service_case.enums import ServiceCaseStatus
from app.domains.service_case.schemas import LinkedServiceCase
from app.integrations.content.models import IngestedContent
from app.integrations.content.normalizer import make_excerpt

logger = get_logger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
TEXT_DISPLAY_TITLE = "正文提交"


def validate_submission_input(input_type: SubmissionInputType, content: str) -> str:
    if content is None or not str(content).strip():
        raise AppException(
            "INVALID_SUBMISSION_INPUT",
            "Submission content is empty",
            status_code=400,
        )
    stripped = str(content).strip()
    if len(stripped.encode("utf-8")) > settings.CONTENT_MAX_BYTES:
        raise AppException(
            "INVALID_SUBMISSION_INPUT",
            "Submission content exceeds the content size limit",
            status_code=400,
        )
    if input_type == SubmissionInputType.URL:
        lowered = stripped.lower()
        if not (lowered.startswith("http://") or lowered.startswith("https://")):
            raise AppException(
                "INVALID_SUBMISSION_INPUT",
                "URL submissions must start with http:// or https://",
                status_code=400,
            )
        if len(stripped) > 1024:
            raise AppException(
                "INVALID_SUBMISSION_INPUT",
                "URL submissions exceed the source URL length limit",
                status_code=400,
            )
        return stripped
    return stripped


def build_input_preview(input_type: SubmissionInputType, content: str) -> str:
    limit = min(settings.CONTENT_EXCERPT_LENGTH, 500)
    if input_type == SubmissionInputType.URL:
        preview = content.strip()
    else:
        preview = _WHITESPACE_RE.sub(" ", content.strip())
    if len(preview) <= limit:
        return preview
    return preview[:limit].rstrip()


def create_user_submission(
    db: Session,
    identity: CurrentIdentity,
    payload: CreateUserSubmissionRequest,
) -> UserSubmissionCreateResponse:
    content = validate_submission_input(payload.input_type, payload.content)
    preview = build_input_preview(payload.input_type, content)
    now = utc_now()
    validate_submission_origin(SubmissionOriginType.USER_INPUT, None)
    submission = UserSubmission(
        user_id=identity.user_id,
        enterprise_id=identity.enterprise_id,
        input_type=payload.input_type.value,
        input_content=content,
        input_preview=preview,
        origin_type=SubmissionOriginType.USER_INPUT.value,
        origin_discovery_id=None,
        status=SubmissionStatus.PENDING.value,
        failure_stage=None,
        source_id=None,
        ingestion_id=None,
        intelligence_run_id=None,
        error_code=None,
        error_message=None,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )
    create_submission(db, submission)
    logger.info(
        "submission created submission_id=%s user_id=%s enterprise_id=%s status=%s "
        "input_type=%s origin_type=%s",
        submission.id,
        submission.user_id,
        submission.enterprise_id,
        submission.status,
        submission.input_type,
        submission.origin_type,
    )
    return build_submission_create_response(db, submission)


def get_user_submission_detail(
    db: Session,
    identity: CurrentIdentity,
    submission_id: UUID,
) -> UserSubmissionDetail:
    submission = require_enterprise_submission(db, identity.enterprise_id, submission_id)
    return build_submission_detail(db, submission)


def list_user_submissions(
    db: Session,
    identity: CurrentIdentity,
    *,
    status: SubmissionStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> UserSubmissionListResponse:
    submissions = list_submissions_for_enterprise(
        db,
        identity.enterprise_id,
        status=None if status is None else status.value,
        limit=limit,
        offset=offset,
    )
    return _build_list_response(db, submissions, limit=limit, offset=offset)


def list_my_user_submissions(
    db: Session,
    identity: CurrentIdentity,
    *,
    status: SubmissionStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> UserSubmissionListResponse:
    submissions = list_submissions_for_user(
        db,
        enterprise_id=identity.enterprise_id,
        user_id=identity.user_id,
        status=None if status is None else status.value,
        limit=limit,
        offset=offset,
    )
    return _build_list_response(db, submissions, limit=limit, offset=offset)


def build_submission_detail(db: Session, submission: UserSubmission) -> UserSubmissionDetail:
    user = get_user_by_id(db, submission.user_id)
    if user is None:
        raise NotFoundException("User not found", code="USER_NOT_FOUND")
    enterprise = get_enterprise(db, submission.enterprise_id)
    if enterprise is None:
        raise NotFoundException("Enterprise not found", code="ENTERPRISE_NOT_FOUND")

    ingestion = None
    if submission.ingestion_id is not None:
        ingestion = db.get(IngestedContent, submission.ingestion_id)

    run = None
    result = None
    if submission.intelligence_run_id is not None:
        run = db.get(IntelligenceRun, submission.intelligence_run_id)
        if run is not None:
            result = _safe_intelligence_result(run)

    content = None
    if ingestion is not None:
        content = SubmissionContentSummary(
            title=ingestion.raw_title,
            publisher=ingestion.raw_publisher,
            resolved_url=ingestion.resolved_url,
            excerpt=make_excerpt(ingestion.normalized_text),
            fetch_status=ingestion.fetch_status,
            extraction_status=ingestion.extraction_status,
            warnings=list(ingestion.warnings or []),
        )

    intelligence = None
    if run is not None:
        intelligence = SubmissionIntelligenceSummary(
            run_id=run.id,
            status=run.status,
            result=result,
        )

    return UserSubmissionDetail(
        submission=SubmissionRecord(
            id=submission.id,
            status=SubmissionStatus(submission.status),
            failure_stage=submission.failure_stage,
            input_type=SubmissionInputType(submission.input_type),
            input_content=submission.input_content,
            input_preview=submission.input_preview,
            origin_type=_origin_type(submission),
            origin_discovery_id=submission.origin_discovery_id,
            source_id=submission.source_id,
            ingestion_id=submission.ingestion_id,
            intelligence_run_id=submission.intelligence_run_id,
            error_code=submission.error_code,
            error_message=submission.error_message,
            created_at=submission.created_at,
            updated_at=submission.updated_at,
            completed_at=submission.completed_at,
        ),
        submitted_by=MeUser.model_validate(user),
        enterprise=MeEnterprise.model_validate(enterprise),
        content=content,
        intelligence=intelligence,
        linked_service_case=_linked_service_case(db, submission.id),
    )


def compute_display_title(
    submission: UserSubmission,
    ingestion: IngestedContent | None,
    run: IntelligenceRun | None,
) -> str:
    result = _safe_intelligence_result(run) if run is not None else None
    claim = result.opportunity_claim if result is not None else None
    claimed_title = (claim.claimed_title or "").strip() if claim is not None else ""
    if claimed_title:
        return claimed_title
    ingested_title = (ingestion.raw_title or "").strip() if ingestion is not None else ""
    if ingested_title:
        return ingested_title
    if submission.input_type == SubmissionInputType.URL.value:
        host = urlparse(submission.input_content).hostname
        if host:
            return host
        return submission.input_preview or TEXT_DISPLAY_TITLE
    return TEXT_DISPLAY_TITLE


def require_enterprise_submission(
    db: Session,
    enterprise_id: UUID,
    submission_id: UUID,
) -> UserSubmission:
    submission = get_submission_for_enterprise(db, submission_id, enterprise_id)
    if submission is None:
        raise NotFoundException("Submission not found", code="SUBMISSION_NOT_FOUND")
    return submission


def build_submission_create_response(
    db: Session,
    submission: UserSubmission,
) -> UserSubmissionCreateResponse:
    user = get_user_by_id(db, submission.user_id)
    if user is None:
        raise NotFoundException("User not found", code="USER_NOT_FOUND")
    enterprise = get_enterprise(db, submission.enterprise_id)
    if enterprise is None:
        raise NotFoundException("Enterprise not found", code="ENTERPRISE_NOT_FOUND")
    return UserSubmissionCreateResponse(
        id=submission.id,
        status=SubmissionStatus(submission.status),
        input_type=SubmissionInputType(submission.input_type),
        input_preview=submission.input_preview,
        origin_type=_origin_type(submission),
        origin_discovery_id=submission.origin_discovery_id,
        created_at=submission.created_at,
        user=UserActor.model_validate(user),
        enterprise=MeEnterprise.model_validate(enterprise),
    )


def validate_submission_origin(
    origin_type: SubmissionOriginType,
    origin_discovery_id: UUID | None,
) -> None:
    if origin_type == SubmissionOriginType.USER_INPUT:
        if origin_discovery_id is not None:
            raise AppException(
                "INVALID_SUBMISSION_ORIGIN",
                "user_input submissions cannot reference a Discovery",
                status_code=400,
            )
        return
    if origin_type == SubmissionOriginType.DISCOVERY:
        if origin_discovery_id is None:
            raise AppException(
                "INVALID_SUBMISSION_ORIGIN",
                "discovery submissions must reference a Discovery",
                status_code=400,
            )
        return
    raise AppException(
        "INVALID_SUBMISSION_ORIGIN",
        "Unknown submission origin",
        status_code=400,
    )


def _build_list_response(
    db: Session,
    submissions: list[UserSubmission],
    *,
    limit: int,
    offset: int,
) -> UserSubmissionListResponse:
    users = _load_users(db, {item.user_id for item in submissions})
    ingestions = _load_ingestions(db, {item.ingestion_id for item in submissions if item.ingestion_id})
    runs = _load_runs(db, {item.intelligence_run_id for item in submissions if item.intelligence_run_id})
    cases = _load_service_cases(db, {item.id for item in submissions})
    items: list[UserSubmissionSummary] = []
    for submission in submissions:
        user = users.get(submission.user_id)
        ingestion = ingestions.get(submission.ingestion_id) if submission.ingestion_id else None
        run = runs.get(submission.intelligence_run_id) if submission.intelligence_run_id else None
        items.append(
            UserSubmissionSummary(
                id=submission.id,
                status=SubmissionStatus(submission.status),
                failure_stage=submission.failure_stage,
                input_type=SubmissionInputType(submission.input_type),
                input_preview=submission.input_preview,
                display_title=compute_display_title(submission, ingestion, run),
                submitted_by=UserActor(
                    id=user.id if user is not None else submission.user_id,
                    display_name=user.display_name if user is not None else "Unknown",
                ),
                origin_type=_origin_type(submission),
                origin_discovery_id=submission.origin_discovery_id,
                source_id=submission.source_id,
                ingestion_id=submission.ingestion_id,
                intelligence_run_id=submission.intelligence_run_id,
                created_at=submission.created_at,
                completed_at=submission.completed_at,
                linked_service_case=_to_linked_service_case(cases.get(submission.id)),
            )
        )
    return UserSubmissionListResponse(items=items, limit=limit, offset=offset)


def _origin_type(submission: UserSubmission) -> SubmissionOriginType:
    value = submission.origin_type or SubmissionOriginType.USER_INPUT.value
    return SubmissionOriginType(value)


def _load_users(db: Session, user_ids: set[UUID]) -> dict[UUID, User]:
    if not user_ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(user_ids))).all()
    return {row.id: row for row in rows}


def _load_ingestions(db: Session, ingestion_ids: set[UUID]) -> dict[UUID, IngestedContent]:
    if not ingestion_ids:
        return {}
    rows = db.scalars(select(IngestedContent).where(IngestedContent.id.in_(ingestion_ids))).all()
    return {row.id: row for row in rows}


def _load_runs(db: Session, run_ids: set[UUID]) -> dict[UUID, IntelligenceRun]:
    if not run_ids:
        return {}
    rows = db.scalars(select(IntelligenceRun).where(IntelligenceRun.id.in_(run_ids))).all()
    return {row.id: row for row in rows}


def _load_service_cases(db: Session, submission_ids: set[UUID]):
    from app.domains.service_case.repository import get_cases_by_submission_ids

    return get_cases_by_submission_ids(db, submission_ids)


def _linked_service_case(db: Session, submission_id: UUID):
    from app.domains.service_case.repository import get_service_case_by_submission_id

    return _to_linked_service_case(get_service_case_by_submission_id(db, submission_id))


def _to_linked_service_case(case) -> LinkedServiceCase | None:
    if case is None:
        return None
    return LinkedServiceCase(
        id=case.id,
        status=ServiceCaseStatus(case.status),
        created_at=case.created_at,
        updated_at=case.updated_at,
        completed_at=case.completed_at,
        closed_at=case.closed_at,
    )


def _safe_intelligence_result(run: IntelligenceRun) -> ContentIntelligenceResult | None:
    try:
        return load_intelligence_result(run)
    except Exception:
        return None
