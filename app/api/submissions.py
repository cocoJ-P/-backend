"""UserSubmission HTTP API. Requires development identity."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.identity.dependencies import get_current_identity
from app.domains.identity.schemas import CurrentIdentity
from app.domains.submission.enums import SubmissionStatus
from app.domains.submission.orchestration import SubmissionOrchestrator
from app.domains.submission.schemas import (
    CreateUserSubmissionRequest,
    UserSubmissionCreateResponse,
    UserSubmissionDetail,
    UserSubmissionListResponse,
)
from app.domains.service_case.schemas import CreateServiceCaseResponse
from app.domains.submission.service import (
    create_user_submission,
    get_user_submission_detail,
    list_my_user_submissions,
    list_user_submissions,
)
from app.domains.service_case.service import create_service_case_for_submission
from app.integrations.feishu.outbound import schedule_service_case_feishu_sync

router = APIRouter(prefix="/user-submissions", tags=["User Submissions"])


@router.post(
    "",
    response_model=UserSubmissionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_submission(
    payload: CreateUserSubmissionRequest,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> UserSubmissionCreateResponse:
    return create_user_submission(db, identity, payload)


@router.post(
    "/{submission_id}/process",
    response_model=UserSubmissionDetail,
)
def process_submission(
    submission_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> UserSubmissionDetail:
    return SubmissionOrchestrator(db).process(submission_id, identity)


@router.post(
    "/{submission_id}/service-case",
    response_model=CreateServiceCaseResponse,
)
def create_service_case(
    submission_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CreateServiceCaseResponse:
    result = create_service_case_for_submission(db, identity, submission_id)
    if result.created:
        schedule_service_case_feishu_sync(db, result.service_case.id, background_tasks)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return result


@router.get(
    "",
    response_model=UserSubmissionListResponse,
)
def list_submissions(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    status_filter: Annotated[SubmissionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> UserSubmissionListResponse:
    return list_user_submissions(
        db,
        identity,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/mine",
    response_model=UserSubmissionListResponse,
)
def list_my_submissions(
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    status_filter: Annotated[SubmissionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> UserSubmissionListResponse:
    return list_my_user_submissions(
        db,
        identity,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{submission_id}",
    response_model=UserSubmissionDetail,
)
def get_submission(
    submission_id: UUID,
    identity: Annotated[CurrentIdentity, Depends(get_current_identity)],
    db: Session = Depends(get_db),
) -> UserSubmissionDetail:
    return get_user_submission_detail(db, identity, submission_id)
