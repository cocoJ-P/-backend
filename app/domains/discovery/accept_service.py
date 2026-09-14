"""Accept a Discovery into the current user's UserSubmission workflow.

Short database transaction only. Does not ingest content or call LLM.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.logging import get_logger
from app.core.time import utc_now
from app.domains.discovery.enums import DiscoveryDisposition, DiscoveryStatus
from app.domains.discovery.models import DiscoveryItem
from app.domains.discovery.schemas import AcceptDiscoveryResponse
from app.domains.discovery.service import require_enterprise_discovery
from app.domains.discovery.user_state_models import DiscoveryUserState
from app.domains.discovery.user_state_repository import get_user_state
from app.domains.discovery.user_state_schemas import DiscoveryUserStateResponse
from app.domains.identity.schemas import CurrentIdentity
from app.domains.submission.enums import SubmissionInputType, SubmissionOriginType, SubmissionStatus
from app.domains.submission.models import UserSubmission
from app.domains.submission.repository import add_submission, get_discovery_origin_submission
from app.domains.submission.service import (
    build_input_preview,
    build_submission_create_response,
    validate_submission_input,
    validate_submission_origin,
)

logger = get_logger(__name__)


def accept_discovery(
    db: Session,
    identity: CurrentIdentity,
    discovery_id: UUID,
) -> AcceptDiscoveryResponse:
    try:
        return _accept_in_transaction(db, identity, discovery_id)
    except IntegrityError:
        db.rollback()
        return _accept_in_transaction(db, identity, discovery_id)


def map_discovery_to_submission_input(item: DiscoveryItem) -> tuple[SubmissionInputType, str]:
    url = (item.reference_url or "").strip()
    if url.lower().startswith("http://") or url.lower().startswith("https://"):
        return SubmissionInputType.URL, url

    parts = [item.title.strip()]
    summary = (item.summary or "").strip()
    if summary:
        parts.append(summary)
    extras: list[str] = []
    issuer = (item.issuer or "").strip()
    if issuer:
        extras.append(f"发布机构：{issuer}")
    region = (item.region or "").strip()
    if region:
        extras.append(f"地区：{region}")
    if item.deadline is not None:
        extras.append(f"截止日期：{item.deadline.isoformat()}")
    if extras:
        parts.append("\n".join(extras))
    return SubmissionInputType.TEXT, "\n\n".join(parts)


def _accept_in_transaction(
    db: Session,
    identity: CurrentIdentity,
    discovery_id: UUID,
) -> AcceptDiscoveryResponse:
    discovery = require_enterprise_discovery(db, identity.enterprise_id, discovery_id)
    _require_active_discovery(discovery)
    state = _ensure_saved_state_flush(db, discovery, identity.user_id)
    existing = get_discovery_origin_submission(
        db,
        enterprise_id=identity.enterprise_id,
        user_id=identity.user_id,
        origin_discovery_id=discovery.id,
    )
    created = False
    if existing is None:
        existing = _create_discovery_submission(db, identity, discovery)
        created = True
    db.commit()
    db.refresh(state)
    db.refresh(existing)
    logger.info(
        "discovery accepted discovery_id=%s user_id=%s enterprise_id=%s "
        "submission_id=%s created=%s",
        discovery.id,
        identity.user_id,
        identity.enterprise_id,
        existing.id,
        created,
    )
    return AcceptDiscoveryResponse(
        created=created,
        user_state=_to_state_response(state),
        submission=build_submission_create_response(db, existing),
    )


def _require_active_discovery(discovery: DiscoveryItem) -> None:
    if discovery.status == DiscoveryStatus.ACTIVE.value:
        return
    logger.info(
        "discovery accept rejected discovery_id=%s enterprise_id=%s status=%s",
        discovery.id,
        discovery.enterprise_id,
        discovery.status,
    )
    raise AppException(
        "DISCOVERY_NOT_ACTIVE",
        "Discovery is not active",
        status_code=409,
    )


def _ensure_saved_state_flush(
    db: Session,
    discovery: DiscoveryItem,
    user_id: UUID,
) -> DiscoveryUserState:
    now = utc_now()
    state = get_user_state(db, discovery.id, user_id)
    if state is None:
        state = DiscoveryUserState(
            discovery_id=discovery.id,
            enterprise_id=discovery.enterprise_id,
            user_id=user_id,
            seen_at=now,
            disposition=DiscoveryDisposition.SAVED.value,
            disposition_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(state)
        db.flush()
        return state

    changed = False
    if state.disposition != DiscoveryDisposition.SAVED.value:
        state.disposition = DiscoveryDisposition.SAVED.value
        state.disposition_at = now
        changed = True
    if state.seen_at is None:
        state.seen_at = now
        changed = True
    if changed:
        state.updated_at = now
        db.add(state)
        db.flush()
    return state


def _create_discovery_submission(
    db: Session,
    identity: CurrentIdentity,
    discovery: DiscoveryItem,
) -> UserSubmission:
    validate_submission_origin(SubmissionOriginType.DISCOVERY, discovery.id)
    input_type, raw_content = map_discovery_to_submission_input(discovery)
    content = validate_submission_input(input_type, raw_content)
    preview = build_input_preview(input_type, content)
    now = utc_now()
    submission = UserSubmission(
        user_id=identity.user_id,
        enterprise_id=identity.enterprise_id,
        input_type=input_type.value,
        input_content=content,
        input_preview=preview,
        origin_type=SubmissionOriginType.DISCOVERY.value,
        origin_discovery_id=discovery.id,
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
    return add_submission(db, submission)


def _to_state_response(state: DiscoveryUserState) -> DiscoveryUserStateResponse:
    return DiscoveryUserStateResponse(
        discovery_id=state.discovery_id,
        user_id=state.user_id,
        seen_at=state.seen_at,
        disposition=state.disposition,
        disposition_at=state.disposition_at,
        updated_at=state.updated_at,
    )
