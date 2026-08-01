"""Tenant- and actor-scoped AgentRun persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.repositories.base import BaseRepository


class AgentRunRepository(BaseRepository):
    """Persist and replay AgentRun registrations inside trusted scope."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(session, tenant_id)

    async def get_for_actor(
        self,
        agent_run_id: UUID,
        actor_id: UUID,
    ) -> AgentRun | None:
        result = await self._session.execute(
            select(AgentRun).where(
                AgentRun.agent_run_id == agent_run_id,
                AgentRun.tenant_id == self._tenant_id,
                AgentRun.actor_id == actor_id,
            )
        )
        return result.scalar_one_or_none()

    def add(self, agent_run: AgentRun) -> None:
        self._session.add(agent_run)
