"""Core-owned AgentRun registration service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.agent import AgentRun
from app.repositories.agent_run_repo import AgentRunRepository
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.agent_run import RegisterAgentRunRequest


class AgentRunService:
    """Create AgentRun rows only after validating their trusted session scope."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._runs = AgentRunRepository(session, tenant_id)
        self._conversations = ConversationRepository(session, tenant_id)

    async def get_for_actor(
        self,
        agent_run_id: UUID,
        actor_id: UUID,
    ) -> AgentRun | None:
        return await self._runs.get_for_actor(agent_run_id, actor_id)

    async def create(
        self,
        *,
        actor_id: UUID,
        request: RegisterAgentRunRequest,
    ) -> AgentRun:
        if request.session_id is not None:
            conversation = await self._conversations.get_for_elder(
                request.session_id,
                request.elder_id,
            )
            if conversation is None:
                raise NotFoundError("Resource not found")
            if conversation.policy_version != request.policy_version:
                raise ConflictError(
                    "Agent run policy version does not match the voice session snapshot"
                )

        agent_run = AgentRun(
            session_id=request.session_id,
            elder_id=request.elder_id,
            tenant_id=self._tenant_id,
            actor_id=actor_id,
            agent_id=request.agent_id,
            agent_version=request.agent_version,
            result_status="RUNNING",
            policy_version=request.policy_version,
            trace_id=request.trace_id,
        )
        self._runs.add(agent_run)
        await self._session.flush()
        return agent_run
