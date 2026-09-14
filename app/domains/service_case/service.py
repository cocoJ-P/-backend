"""Create, list, and transition ServiceCase records.

Does not call Feishu, LLM, or the network. Status mutation is internal.
"""

from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.identity.repository import get_user_by_id
from app.domains.identity.schemas import CurrentIdentity
from app.domains.intelligence.models import IntelligenceRun
from app.domains.service_case.enums import ServiceCaseStatus
from app.domains.service_case.models import ServiceCase
from app.domains.service_case.repository import (
    add_service_case,
    get_service_case_by_submission_id,
    get_service_case_for_enterprise,
    list_service_cases_for_enterprise,
    save_service_case,
)
from app.domains.service_case.schemas import (
    CreateServiceCaseResponse,
    ServiceCaseActor,
    ServiceCaseDetail,
    ServiceCaseDetailSubmissionRef,
    ServiceCaseListItem,
    ServiceCaseListResponse,
    ServiceCaseListSubmissionRef,
    ServiceCaseRecord,
)
from app.domains.submission.enums import SubmissionInputType, SubmissionOriginType, SubmissionStatus
from app.domains.submission.models import UserSubmission
from app.domains.submission.repository import get_submission_for_owner
from app.domains.submission.service import TEXT_DISPLAY_TITLE, compute_display_title
from app.integrations.content.models import IngestedContent

logger = get_logger(__name__)

TITLE_MAX_LENGTH = 512
DEFAULT_SERVICE_CASE_TITLE = "企业服务事项"

ALLOWED_TRANSITIONS: dict[ServiceCaseStatus, set[ServiceCaseStatus]] = {
    ServiceCaseStatus.OPEN: {ServiceCaseStatus.IN_PROGRESS, ServiceCaseStatus.CLOSED},
    ServiceCaseStatus.IN_PROGRESS: {ServiceCaseStatus.COMPLETED, ServiceCaseStatus.CLOSED},
    ServiceCaseStatus.COMPLETED: set(),
    ServiceCaseStatus.CLOSED: set(),
}


def create_service_case_for_submission(
    db: Session,
    identity: CurrentIdentity,
    submission_id: UUID,
) -> CreateServiceCaseResponse:
    try:
        return _create_in_transaction(db, identity, submission_id)
    except IntegrityError:
        db.rollback()
        return _create_in_transaction(db, identity, submission_id)


def list_enterprise_service_cases(
    db: Session,
    identity: CurrentIdentity,
    *,
    status: ServiceCaseStatus | None = None,
    user_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ServiceCaseListResponse:
    rows = list_service_cases_for_enterprise(
        db,
        identity.enterprise_id,
        status=None if status is None else status.value,
        created_by_user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return ServiceCaseListResponse(
        items=[_to_list_item(case, user, submission) for case, user, submission in rows],
        limit=limit,
        offset=offset,
    )


def list_my_service_cases(
    db: Session,
    identity: CurrentIdentity,
    *,
    status: ServiceCaseStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ServiceCaseListResponse:
    return list_enterprise_service_cases(
        db,
        identity,
        status=status,
        user_id=identity.user_id,
        limit=limit,
        offset=offset,
    )


def get_service_case_detail(
    db: Session,
    identity: CurrentIdentity,
    service_case_id: UUID,
) -> ServiceCaseDetail:
    case = get_service_case_for_enterprise(db, service_case_id, identity.enterprise_id)
    if case is None:
        raise NotFoundException("Service case not found", code="SERVICE_CASE_NOT_FOUND")
    user = get_user_by_id(db, case.created_by_user_id)
    if user is None:
        raise NotFoundException("User not found", code="USER_NOT_FOUND")
    submission = db.get(UserSubmission, case.submission_id)
    if submission is None:
        raise NotFoundException("Submission not found", code="SUBMISSION_NOT_FOUND")
    return ServiceCaseDetail(
        id=case.id,
        enterprise_id=case.enterprise_id,
        created_by_user_id=case.created_by_user_id,
        submission_id=case.submission_id,
        title=case.title,
        status=ServiceCaseStatus(case.status),
        created_at=case.created_at,
        updated_at=case.updated_at,
        completed_at=case.completed_at,
        closed_at=case.closed_at,
        created_by_user=ServiceCaseActor(id=user.id, display_name=user.display_name),
        submission=ServiceCaseDetailSubmissionRef(
            id=submission.id,
            status=SubmissionStatus(submission.status),
            input_type=SubmissionInputType(submission.input_type),
            input_preview=submission.input_preview,
            origin_type=SubmissionOriginType(submission.origin_type),
            origin_discovery_id=submission.origin_discovery_id,
            created_at=submission.created_at,
            completed_at=submission.completed_at,
        ),
    )


def transition_service_case_status(
    db: Session,
    service_case: ServiceCase,
    target_status: ServiceCaseStatus,
) -> ServiceCase:
    current = ServiceCaseStatus(service_case.status)
    if target_status not in ALLOWED_TRANSITIONS[current]:
        raise AppException(
            "INVALID_SERVICE_CASE_TRANSITION",
            f"Cannot transition service case from {current.value} to {target_status.value}",
            status_code=409,
        )
    now = utc_now()
    service_case.status = target_status.value
    if target_status == ServiceCaseStatus.COMPLETED:
        service_case.completed_at = now
        service_case.closed_at = None
    elif target_status == ServiceCaseStatus.CLOSED:
        service_case.closed_at = now
        service_case.completed_at = None
    save_service_case(db, service_case)
    logger.info(
        "service case transitioned service_case_id=%s from=%s to=%s",
        service_case.id,
        current.value,
        target_status.value,
    )
    return service_case


def generate_service_case_title(db: Session, submission: UserSubmission) -> str:
    ingestion = None
    if submission.ingestion_id is not None:
        ingestion = db.get(IngestedContent, submission.ingestion_id)
    run = None
    if submission.intelligence_run_id is not None:
        run = db.get(IntelligenceRun, submission.intelligence_run_id)
    title = compute_display_title(submission, ingestion, run).strip()
    if title and title != TEXT_DISPLAY_TITLE:
        return title[:TITLE_MAX_LENGTH]
    preview_line = _first_preview_line(submission.input_preview)
    if preview_line:
        return preview_line[:TITLE_MAX_LENGTH]
    if submission.input_type == SubmissionInputType.URL.value:
        host = urlparse(submission.input_content or "").hostname
        if host:
            return host[:TITLE_MAX_LENGTH]
        url = (submission.input_content or "").strip()
        if url:
            return url[:TITLE_MAX_LENGTH]
    return DEFAULT_SERVICE_CASE_TITLE


def _create_in_transaction(
    db: Session,
    identity: CurrentIdentity,
    submission_id: UUID,
) -> CreateServiceCaseResponse:
    submission = get_submission_for_owner(
        db,
        submission_id,
        enterprise_id=identity.enterprise_id,
        user_id=identity.user_id,
    )
    if submission is None:
        raise NotFoundException("Submission not found", code="SUBMISSION_NOT_FOUND")
    if submission.status != SubmissionStatus.SUCCEEDED.value:
        raise AppException(
            "SUBMISSION_NOT_READY_FOR_SERVICE",
            "Submission has not succeeded and cannot enter service handling",
            status_code=409,
        )
    existing = get_service_case_by_submission_id(db, submission.id)
    created = False
    if existing is None:
        now = utc_now()
        existing = ServiceCase(
            enterprise_id=identity.enterprise_id,
            created_by_user_id=identity.user_id,
            submission_id=submission.id,
            title=generate_service_case_title(db, submission),
            status=ServiceCaseStatus.OPEN.value,
            created_at=now,
            updated_at=now,
            completed_at=None,
            closed_at=None,
        )
        add_service_case(db, existing)
        created = True
    db.commit()
    db.refresh(existing)
    logger.info(
        "service case create submission_id=%s service_case_id=%s user_id=%s "
        "enterprise_id=%s created=%s",
        submission.id,
        existing.id,
        identity.user_id,
        identity.enterprise_id,
        created,
    )
    return CreateServiceCaseResponse(created=created, service_case=_to_record(existing))


def _to_record(case: ServiceCase) -> ServiceCaseRecord:
    return ServiceCaseRecord(
        id=case.id,
        enterprise_id=case.enterprise_id,
        created_by_user_id=case.created_by_user_id,
        submission_id=case.submission_id,
        title=case.title,
        status=ServiceCaseStatus(case.status),
        created_at=case.created_at,
        updated_at=case.updated_at,
        completed_at=case.completed_at,
        closed_at=case.closed_at,
    )


def _to_list_item(case: ServiceCase, user, submission: UserSubmission) -> ServiceCaseListItem:
    return ServiceCaseListItem(
        id=case.id,
        title=case.title,
        status=ServiceCaseStatus(case.status),
        created_at=case.created_at,
        updated_at=case.updated_at,
        completed_at=case.completed_at,
        closed_at=case.closed_at,
        created_by_user=ServiceCaseActor(id=user.id, display_name=user.display_name),
        submission=ServiceCaseListSubmissionRef(
            id=submission.id,
            status=SubmissionStatus(submission.status),
            origin_type=SubmissionOriginType(submission.origin_type),
            origin_discovery_id=submission.origin_discovery_id,
            created_at=submission.created_at,
        ),
    )


def _first_preview_line(preview: str | None) -> str:
    text = (preview or "").strip()
    if not text:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
