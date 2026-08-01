"""Identity API endpoints.

Implements:
- GET /api/v1/me — returns the authenticated actor's profile
- GET /api/v1/me/authorized-elders — returns paginated elders the actor can access
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.envelopes import ResponseMeta, SuccessEnvelope
from app.core.exceptions import AuthorizationDeniedError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.middleware.auth import ActorContext
from app.middleware.logging import correlation_id_var
from app.models.elder import Elder
from app.repositories.actor_repo import ActorRepository
from app.repositories.care_assignment_repo import CareAssignmentRepository
from app.repositories.care_relationship_repo import CareRelationshipRepository
from app.repositories.care_unit_membership_repo import CareUnitMembershipRepository
from app.repositories.tenant_membership_repo import TenantMembershipRepository
from app.schemas.identity import (
    AuthorizedElderItem,
    AuthorizedEldersResponse,
    ElderMode,
    MeResponse,
    PaginationMeta,
)
from app.services.identity_service import IdentityService

router = APIRouter(prefix="/api/v1", tags=["identity"])


def _build_identity_service(session: AsyncSession, actor_context: ActorContext) -> IdentityService:
    """Construct IdentityService with all required repositories."""
    return IdentityService(
        actor_repo=ActorRepository(session),
        tenant_membership_repo=TenantMembershipRepository(session),
        care_unit_membership_repo=CareUnitMembershipRepository(session),
        care_relationship_repo=CareRelationshipRepository(session, actor_context.tenant_id),
        care_assignment_repo=CareAssignmentRepository(session, actor_context.tenant_id),
    )


def _get_correlation_id() -> str:
    """Read the correlation_id from the request-scoped contextvar."""
    cid = correlation_id_var.get()
    if not cid:
        import uuid

        cid = str(uuid.uuid4())
    return cid


@router.get("/me")
async def get_me(
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return the authenticated actor's profile.

    Includes actor identity fields and the list of care unit IDs
    the actor belongs to.
    """
    service = _build_identity_service(session, actor_context)
    profile = await service.get_actor_profile(actor_context, datetime.now(UTC))

    elder_id = None
    if profile.actor_type == "ELDER":
        elder_ids = list(
            (
                await session.execute(
                    select(Elder.id).where(
                        Elder.actor_id == actor_context.actor_id,
                        Elder.tenant_id == actor_context.tenant_id,
                        Elder.status == "ACTIVE",
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(elder_ids) != 1:
            raise AuthorizationDeniedError("Resource not found")
        elder_id = elder_ids[0]

    me_response = MeResponse(
        actor_id=profile.actor_id,
        actor_type=profile.actor_type,
        display_name=profile.display_name,
        tenant_id=profile.tenant_id,
        role=profile.role,
        care_unit_ids=profile.care_unit_ids,
        elder_id=elder_id,
    )

    return SuccessEnvelope(
        data=me_response,
        meta=ResponseMeta(
            correlation_id=_get_correlation_id(),
            timestamp=datetime.now(UTC),
        ),
    ).model_dump(mode="json")


@router.get("/me/authorized-elders")
async def get_authorized_elders(
    mode: ElderMode = Query(..., description="Access mode: daycare, home-care, or family"),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor"),
    limit: int = Query(default=20, ge=1, le=100, description="Page size (1–100)"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return paginated elders the actor is authorized to access.

    Mode must be compatible with the actor's role. Incompatible
    combinations return 403 via RoleModeIncompatibleError.
    """
    service = _build_identity_service(session, actor_context)
    current_time = datetime.now(UTC)

    result = await service.get_authorized_elders(
        actor_context=actor_context,
        mode=mode.value,
        current_time=current_time,
        cursor=cursor,
        limit=limit,
    )

    items = [
        AuthorizedElderItem(
            elder_id=row.elder_id,
            display_name=row.display_name,
            care_unit_name=row.care_unit_name,
            authorization_summary=f"{mode.value} authorization",
        )
        for row in result.items
    ]

    elders_response = AuthorizedEldersResponse(
        items=items,
        page=PaginationMeta(
            next_cursor=result.next_cursor,
            has_more=result.has_more,
            limit=limit,
        ),
    )

    return SuccessEnvelope(
        data=elders_response,
        meta=ResponseMeta(
            correlation_id=_get_correlation_id(),
            timestamp=datetime.now(UTC),
        ),
    ).model_dump(mode="json")
