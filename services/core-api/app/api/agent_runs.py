"""Internal Core-owned AgentRun registration and completion endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import success
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_system_service_actor
from app.middleware.auth import ActorContext
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.agent_run import (
    AgentRunCompletionResponse,
    AgentRunRegistrationResponse,
    CompleteAgentRunRequest,
    RegisterAgentRunRequest,
)
from app.services.agent_run_service import AgentRunService
from app.services.authorization_service import authorize_elder

router = APIRouter(prefix="/api/v1/internal", tags=["agent-runs"])


def _registration_response(agent_run) -> dict:
    return AgentRunRegistrationResponse(
        agent_run_id=agent_run.agent_run_id,
        session_id=agent_run.session_id,
        elder_id=agent_run.elder_id,
        agent_id=agent_run.agent_id,
        agent_version=agent_run.agent_version,
        result_status="RUNNING",
        policy_version=agent_run.policy_version,
        trace_id=agent_run.trace_id,
    ).model_dump(mode="json")


def _completion_response(agent_run) -> dict:
    return AgentRunCompletionResponse(
        agent_run_id=agent_run.agent_run_id,
        session_id=agent_run.session_id,
        elder_id=agent_run.elder_id,
        agent_id=agent_run.agent_id,
        agent_version=agent_run.agent_version,
        result_status=agent_run.result_status,
        policy_version=agent_run.policy_version,
        trace_id=agent_run.trace_id,
        stop_reason=agent_run.stop_reason,
        completed_at=agent_run.completed_at,
    ).model_dump(mode="json")


@router.post("/agent-runs", status_code=status.HTTP_201_CREATED)
async def register_agent_run(
    request: RegisterAgentRunRequest,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
        max_length=160,
    ),
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(
        session,
        actor_context,
        request.elder_id,
        "agent_run:create",
    )
    idempotency = IdempotencyRepository(
        session,
        actor_context.tenant_id,
        actor_context.actor_id,
    )
    replay = await idempotency.begin(
        key=idempotency_key,
        operation="register_agent_run",
        payload=request.model_dump(mode="json"),
    )
    service = AgentRunService(session, actor_context.tenant_id)
    if replay.replayed:
        agent_run = (
            await service.get_for_actor(replay.resource_id, actor_context.actor_id)
            if replay.resource_id is not None
            else None
        )
        if agent_run is None:
            raise NotFoundError("Resource not found")
    else:
        agent_run = await service.create(
            actor_id=actor_context.actor_id,
            request=request,
        )
        response = _registration_response(agent_run)
        await idempotency.complete(
            key=idempotency_key,
            resource_type="agent_run",
            resource_id=agent_run.agent_run_id,
            response_status=status.HTTP_201_CREATED,
            response_body=response,
        )

    return success(_registration_response(agent_run))


@router.post("/agent-runs/{agent_run_id}/complete")
async def complete_agent_run(
    request: CompleteAgentRunRequest,
    agent_run_id: UUID = Path(...),
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
        max_length=160,
    ),
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    idempotency = IdempotencyRepository(
        session,
        actor_context.tenant_id,
        actor_context.actor_id,
    )
    replay = await idempotency.begin(
        key=idempotency_key,
        operation="complete_agent_run",
        payload={
            "agent_run_id": agent_run_id,
            **request.model_dump(mode="json"),
        },
    )
    service = AgentRunService(session, actor_context.tenant_id)
    if replay.replayed:
        if replay.resource_type != "agent_run" or replay.resource_id != agent_run_id:
            raise ConflictError("Idempotency replay does not match the AgentRun completion")
        agent_run = await service.get_for_actor(agent_run_id, actor_context.actor_id)
        if agent_run is None:
            raise NotFoundError("Resource not found")
        service.require_matching_completion(agent_run, request)
    else:
        agent_run = await service.complete(
            agent_run_id=agent_run_id,
            actor_id=actor_context.actor_id,
            request=request,
        )
        response = _completion_response(agent_run)
        await idempotency.complete(
            key=idempotency_key,
            resource_type="agent_run",
            resource_id=agent_run.agent_run_id,
            response_status=status.HTTP_200_OK,
            response_body=response,
        )

    return success(_completion_response(agent_run))
