"""Elder-only family invitation management endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.middleware.auth import ActorContext
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.family_invitation import CreateFamilyInvitationRequest
from app.services.family_invitation_service import FamilyInvitationService
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec
from app.services.service_dependencies import get_family_invitation_token_codec

router = APIRouter(prefix="/api/v1", tags=["family-invitations"])


@router.post(
    "/elders/{elder_id}/family-invitations",
    status_code=status.HTTP_201_CREATED,
)
async def create_family_invitation(
    request: CreateFamilyInvitationRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    codec: FamilyInvitationTokenCodec = Depends(get_family_invitation_token_codec),
) -> dict:
    idem = IdempotencyRepository(session, actor.tenant_id, actor.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_family_invitation",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    if replay.replayed:
        # Only a hash of the one-time code is retained, so replaying the
        # plaintext response is deliberately impossible.
        raise ConflictError("Invitation was already issued; create a new invitation if needed")
    result = await FamilyInvitationService(session, codec).create(
        tenant_id=actor.tenant_id,
        elder_id=elder_id,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        request=request,
        trace_id=get_correlation_id(),
        idempotency_key=idempotency_key,
    )
    await idem.complete(
        key=idempotency_key,
        resource_type="family_invitation",
        resource_id=result.invitation_id,
        response_status=status.HTTP_201_CREATED,
        response_body={"invitation_id": str(result.invitation_id)},
    )
    return success(result.model_dump(mode="json"))


@router.get("/elders/{elder_id}/family-invitations")
async def list_family_invitations(
    elder_id: UUID = Path(...),
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    codec: FamilyInvitationTokenCodec = Depends(get_family_invitation_token_codec),
) -> dict:
    result = await FamilyInvitationService(session, codec).list_for_elder(
        tenant_id=actor.tenant_id,
        elder_id=elder_id,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
    )
    return success(result.model_dump(mode="json"))


@router.post("/elders/{elder_id}/family-invitations/{invitation_id}/revoke")
async def revoke_family_invitation(
    elder_id: UUID = Path(...),
    invitation_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    codec: FamilyInvitationTokenCodec = Depends(get_family_invitation_token_codec),
) -> dict:
    idem = IdempotencyRepository(session, actor.tenant_id, actor.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="revoke_family_invitation",
        payload={"elder_id": elder_id, "invitation_id": invitation_id},
    )
    service = FamilyInvitationService(session, codec)
    if replay.replayed:
        rows = await service.list_for_elder(
            tenant_id=actor.tenant_id,
            elder_id=elder_id,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
        )
        result = next(
            (item for item in rows.items if item.invitation_id == invitation_id),
            None,
        )
        if result is None:
            raise NotFoundError("Resource not found")
    else:
        result = await service.revoke(
            tenant_id=actor.tenant_id,
            elder_id=elder_id,
            invitation_id=invitation_id,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="family_invitation",
            resource_id=invitation_id,
            response_status=status.HTTP_200_OK,
            response_body={"invitation_id": str(invitation_id), "status": result.status},
        )
    return success(result.model_dump(mode="json"))
