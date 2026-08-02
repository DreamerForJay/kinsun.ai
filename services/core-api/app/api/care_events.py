"""Care-event candidate, listing, detail, and review endpoints."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.cursor import decode_cursor, encode_cursor
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.middleware.auth import ActorContext
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.care_event import (
    EVIDENCE_REF_PATTERN,
    CareEventListResponse,
    CareEventResponse,
    CareEventReviewResponse,
    CareEventType,
    ConfidenceBand,
    CreateCareEventCandidateRequest,
    ReviewCareEventRequest,
)
from app.services.authorization_service import authorize_elder
from app.services.care_event_service import CareEventService

router = APIRouter(prefix="/api/v1", tags=["care-events"])

CareEventReadStatus = Literal[
    "CANDIDATE",
    "NEEDS_REVIEW",
    "VERIFIED",
    "CORRECTED",
    "REJECTED",
    "EXCLUDED",
]
REVIEWABLE_CARE_EVENT_STATUSES = (
    "CANDIDATE",
    "NEEDS_REVIEW",
    "VERIFIED",
    "CORRECTED",
    "REJECTED",
    "EXCLUDED",
)
ALLOWED_STATUSES = frozenset(REVIEWABLE_CARE_EVENT_STATUSES)
FORMAL_CARE_EVENT_STATUSES = ("VERIFIED", "CORRECTED")
EVIDENCE_REF_RE = re.compile(EVIDENCE_REF_PATTERN)


def _band(confidence: Decimal | None) -> ConfidenceBand:
    if confidence is None or confidence < Decimal("0.5000"):
        return ConfidenceBand.LOW
    if confidence < Decimal("0.8000"):
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.HIGH


def _safe_evidence_refs(value: str | None) -> list[str]:
    """Return only bounded opaque references from persisted event evidence."""
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [
        ref for ref in parsed if isinstance(ref, str) and EVIDENCE_REF_RE.fullmatch(ref) is not None
    ][:16]


async def _response(service: CareEventService, event) -> CareEventResponse:
    version = await service.get_version(event)
    return CareEventResponse(
        event_id=event.id,
        elder_id=event.elder_id,
        event_type=event.event_type,
        event_time=event.event_time,
        status=event.status,
        structured_payload=version.structured_payload,
        evidence_refs=_safe_evidence_refs(version.evidence_text_ref),
        confidence_band=_band(version.confidence),
        version=event.current_version,
        consent_version=event.consent_version,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


@router.post(
    "/elders/{elder_id}/care-event-candidates",
    status_code=status.HTTP_201_CREATED,
)
async def create_care_event_candidate(
    request: CreateCareEventCandidateRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "care_event:candidate:create")
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_care_event_candidate",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    service = CareEventService(session, actor_context.tenant_id)
    if replay.replayed:
        event = (
            await service.get(elder_id, replay.resource_id)
            if replay.resource_id is not None
            else None
        )
        if event is None:
            raise NotFoundError("Resource not found")
    else:
        event = await service.create_candidate(
            elder_id=elder_id,
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        body = (await _response(service, event)).model_dump(mode="json")
        await idem.complete(
            key=idempotency_key,
            resource_type="care_event",
            resource_id=event.id,
            response_status=status.HTTP_201_CREATED,
            response_body=body,
        )
    return success((await _response(service, event)).model_dump(mode="json"))


@router.get("/elders/{elder_id}/care-events")
async def list_care_events(
    elder_id: UUID = Path(...),
    event_status: list[CareEventReadStatus] | None = Query(
        default=None,
        alias="status",
        description=(
            "Defaults to formal VERIFIED and CORRECTED events. "
            "Any supported explicit non-formal status additionally requires "
            "care_event:review. DELETED events are never returned."
        ),
    ),
    event_type: CareEventType | None = Query(
        default=None,
        description="Exact event type filter applied before cursor pagination.",
    ),
    date_from: date | None = Query(
        default=None,
        description=(
            "Inclusive UTC date for COALESCE(event_time, created_at), applied before pagination."
        ),
    ),
    date_to: date | None = Query(
        default=None,
        description=(
            "Inclusive UTC date for COALESCE(event_time, created_at), applied before pagination."
        ),
    ),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """List scoped events with server-side filters before opaque pagination."""
    await authorize_elder(session, actor_context, elder_id, "care_event:read")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValidationError(
            details=[
                {
                    "field": "date_from",
                    "reason": "date_from must be on or before date_to",
                }
            ]
        )
    requested_statuses = event_status or list(FORMAL_CARE_EVENT_STATUSES)
    if not set(requested_statuses).issubset(ALLOWED_STATUSES):
        raise ValidationError(
            details=[{"field": "status", "reason": "status contains an unsupported value"}]
        )
    if set(requested_statuses).difference(FORMAL_CARE_EVENT_STATUSES):
        await authorize_elder(session, actor_context, elder_id, "care_event:review")
    service = CareEventService(session, actor_context.tenant_id)
    events = await service.list_for_elder(
        elder_id=elder_id,
        statuses=requested_statuses,
        event_type=event_type.value if event_type is not None else None,
        event_time_from=(
            datetime.combine(date_from, time.min, tzinfo=UTC) if date_from is not None else None
        ),
        event_time_to=(
            datetime.combine(date_to, time.max, tzinfo=UTC) if date_to is not None else None
        ),
        limit=limit,
        cursor=decode_cursor(cursor) if cursor else None,
    )
    has_more = len(events) > limit
    page = events[:limit]
    items = [(await _response(service, event)) for event in page]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
    return success(
        CareEventListResponse(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
        ).model_dump(mode="json")
    )


@router.get("/elders/{elder_id}/care-events/{event_id}")
async def get_care_event(
    elder_id: UUID = Path(...),
    event_id: UUID = Path(...),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return a non-deleted event; non-formal states require a reviewer."""
    await authorize_elder(session, actor_context, elder_id, "care_event:read")
    service = CareEventService(session, actor_context.tenant_id)
    event = await service.get(
        elder_id,
        event_id,
        statuses=list(FORMAL_CARE_EVENT_STATUSES),
    )
    if event is None:
        await authorize_elder(session, actor_context, elder_id, "care_event:review")
        event = await service.get(
            elder_id,
            event_id,
            statuses=list(REVIEWABLE_CARE_EVENT_STATUSES),
        )
    if event is None:
        raise NotFoundError("Resource not found")
    return success((await _response(service, event)).model_dump(mode="json"))


@router.post("/elders/{elder_id}/care-events/{event_id}/review")
async def review_care_event(
    request: ReviewCareEventRequest,
    elder_id: UUID = Path(...),
    event_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "care_event:review")
    service = CareEventService(session, actor_context.tenant_id)
    event = await service.get(elder_id, event_id)
    if event is None:
        raise NotFoundError("Resource not found")
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="review_care_event",
        payload={
            "elder_id": elder_id,
            "event_id": event_id,
            **request.model_dump(mode="json"),
        },
    )
    rebuild_required: list[str] = []
    if replay.replayed:
        review = await service.get_latest_review(event.id)
        if review is None:
            raise NotFoundError("Resource not found")
    else:
        review, rebuild_required = await service.review(
            event=event,
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="care_event",
            resource_id=event.id,
            response_status=200,
            response_body={
                "event_id": str(event.id),
                "review_record_id": str(review.review_id),
                "status": event.status,
            },
        )
    base = (await _response(service, event)).model_dump()
    response = CareEventReviewResponse(
        **base,
        review_record_id=review.review_id,
        rebuild_required=rebuild_required,
    )
    return success(response.model_dump(mode="json"))
