"""Core-owned conversation-session REST endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.agent_runtime import AgentRuntimeClient, get_agent_runtime_client
from app.api.responses import get_correlation_id, success
from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import (
    require_active_actor,
    require_system_service_actor,
)
from app.middleware.auth import ActorContext
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.conversation import (
    CompanionTurnRequest,
    ConsumeVoiceTicketRequest,
    CreateVoiceSessionRequest,
    CreateVoiceTicketRequest,
    TransitionVoiceSessionRequest,
    VoiceSessionResponse,
    VoiceTicketIssuedResponse,
)
from app.services.authorization_service import authorize_elder
from app.services.companion_service import CompanionService
from app.services.conversation_service import ConversationService
from app.services.voice_ticket_codec import (
    IssuedVoiceTicket,
    VoiceTicketCodec,
    get_voice_ticket_codec,
)

router = APIRouter(prefix="/api/v1", tags=["voice-sessions"])


def _response(conversation) -> dict:
    return VoiceSessionResponse(
        session_id=conversation.id,
        elder_id=conversation.elder_id,
        state=conversation.state,
        language_route=conversation.language_route,
        consent_version=conversation.consent_version,
        policy_version=conversation.policy_version,
        started_at=conversation.started_at,
        ended_at=conversation.ended_at,
    ).model_dump(mode="json")


def _ticket_response(conversation, issued: IssuedVoiceTicket) -> dict:
    return VoiceTicketIssuedResponse(
        voice_session=VoiceSessionResponse.model_validate(_response(conversation)),
        voice_ticket=issued.value,
        expires_at=issued.expires_at,
    ).model_dump(mode="json")


@router.post(
    "/elders/{elder_id}/voice-sessions",
    status_code=status.HTTP_201_CREATED,
)
async def create_voice_session(
    request: CreateVoiceSessionRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "voice_session:create")
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_voice_session",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    service = ConversationService(session, actor_context.tenant_id)
    if replay.replayed:
        conversation = (
            await service.get(replay.resource_id) if replay.resource_id is not None else None
        )
        if conversation is None:
            raise NotFoundError("Resource not found")
    else:
        conversation = await service.create(
            elder_id=elder_id,
            actor_id=actor_context.actor_id,
            actor_role=actor_context.actor_role,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="conversation_session",
            resource_id=conversation.id,
            response_status=status.HTTP_201_CREATED,
            response_body=_response(conversation),
        )
    return success(_response(conversation))


@router.post(
    "/elders/{elder_id}/voice-tickets",
    status_code=status.HTTP_201_CREATED,
)
async def issue_voice_ticket(
    request: CreateVoiceTicketRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    codec: VoiceTicketCodec = Depends(get_voice_ticket_codec),
) -> dict:
    """Issue an opaque, short-lived capability from trusted server context."""
    await authorize_elder(session, actor_context, elder_id, "voice_session:create")
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="issue_voice_ticket",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    service = ConversationService(session, actor_context.tenant_id)
    if replay.replayed:
        if replay.resource_id is None:
            raise NotFoundError("Resource not found")
        conversation, issued = await service.replay_ticket(replay.resource_id, codec)
    else:
        conversation, issued = await service.issue_ticket(
            elder_id=elder_id,
            actor_id=actor_context.actor_id,
            actor_role=actor_context.actor_role,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
            codec=codec,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="conversation_session",
            resource_id=conversation.id,
            response_status=status.HTTP_201_CREATED,
            response_body={
                "session_id": str(conversation.id),
                "expires_at": issued.expires_at.isoformat(),
            },
        )
    return success(_ticket_response(conversation, issued))


@router.post("/internal/voice-tickets/consume")
async def consume_voice_ticket(
    request: ConsumeVoiceTicketRequest,
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
    codec: VoiceTicketCodec = Depends(get_voice_ticket_codec),
) -> dict:
    """Consume a Ticket once after service identity and live-consent checks."""
    conversation = await ConversationService(
        session,
        actor_context.tenant_id,
    ).consume_ticket(
        session_id=request.session_id,
        value=request.voice_ticket,
        actor_id=actor_context.actor_id,
        trace_id=get_correlation_id(),
        codec=codec,
    )
    return success(_response(conversation))


@router.get("/voice-sessions/{session_id}")
async def get_voice_session(
    session_id: UUID = Path(...),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = ConversationService(session, actor_context.tenant_id)
    conversation = await service.get(session_id)
    if conversation is None:
        raise NotFoundError("Resource not found")
    await authorize_elder(
        session,
        actor_context,
        conversation.elder_id,
        "voice_session:read",
    )
    return success(_response(conversation))


async def _transition_voice_session(
    *,
    session_id: UUID,
    target_state: str,
    idempotency_key: str,
    actor_context: ActorContext,
    session: AsyncSession,
) -> dict:
    service = ConversationService(session, actor_context.tenant_id)
    conversation = await service.get(session_id)
    if conversation is None:
        raise NotFoundError("Resource not found")
    await authorize_elder(
        session,
        actor_context,
        conversation.elder_id,
        "voice_session:control",
    )
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation=f"voice_session_{target_state.lower()}",
        payload={"session_id": session_id},
    )
    if not replay.replayed:
        conversation = await service.transition(
            conversation=conversation,
            target_state=target_state,
            actor_id=actor_context.actor_id,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="conversation_session",
            resource_id=conversation.id,
            response_status=200,
            response_body=_response(conversation),
        )
    return success(_response(conversation))


@router.post("/voice-sessions/{session_id}/cancel")
async def cancel_voice_session(
    session_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _transition_voice_session(
        session_id=session_id,
        target_state="CANCELLED",
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.post("/internal/voice-sessions/{session_id}/transition")
async def transition_voice_session(
    request: TransitionVoiceSessionRequest,
    session_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _transition_voice_session(
        session_id=session_id,
        target_state=request.target_state,
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.post("/voice-sessions/{session_id}/complete")
async def complete_voice_session(
    session_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _transition_voice_session(
        session_id=session_id,
        target_state="COMPLETED",
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.post("/voice-sessions/{session_id}/companion-turns")
async def create_companion_turn(
    request: CompanionTurnRequest,
    session_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    runtime_client: AgentRuntimeClient = Depends(get_agent_runtime_client),
) -> dict:
    """Run one text-only companion turn through Core's authorization gate."""
    conversation_service = ConversationService(session, actor_context.tenant_id)
    conversation = await conversation_service.get(session_id)
    if conversation is None:
        raise NotFoundError("Resource not found")
    await authorize_elder(
        session,
        actor_context,
        conversation.elder_id,
        "voice_session:control",
    )

    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_companion_turn",
        payload={"session_id": session_id, "input_text": request.input_text},
    )
    if replay.replayed:
        raise ConflictError("Companion turn already completed; create a new session")

    settings = get_settings()
    response = await CompanionService(
        session,
        actor_context.tenant_id,
        runtime_client,
        settings.agent_runtime_model_id,
    ).run_turn(
        conversation=conversation,
        actor_context=actor_context,
        input_text=request.input_text,
        correlation_id=get_correlation_id(),
        idempotency_key=idempotency_key,
        latency_budget_ms=min(
            300_000,
            max(100, round(settings.agent_runtime_timeout_seconds * 1000)),
        ),
    )
    await idem.complete(
        key=idempotency_key,
        resource_type="agent_run",
        resource_id=response.agent_run_id,
        response_status=200,
        response_body=response.model_dump(mode="json"),
    )
    return success(response.model_dump(mode="json"))
