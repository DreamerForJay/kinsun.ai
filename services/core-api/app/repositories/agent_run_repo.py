"""Tenant- and actor-scoped AgentRun lifecycle persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.repositories.base import BaseRepository


class AgentRunRepository(BaseRepository):
    """Persist registrations and complete RUNNING rows with one atomic CAS."""

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

    async def complete_running_for_actor(
        self,
        *,
        agent_run_id: UUID,
        actor_id: UUID,
        result_status: str,
        stop_reason: str | None,
        completed_at: datetime,
    ) -> AgentRun | None:
        result = await self._session.execute(
            update(AgentRun)
            .where(
                AgentRun.agent_run_id == agent_run_id,
                AgentRun.tenant_id == self._tenant_id,
                AgentRun.actor_id == actor_id,
                AgentRun.result_status == "RUNNING",
            )
            .values(
                result_status=result_status,
                stop_reason=stop_reason,
                completed_at=completed_at,
            )
            .returning(AgentRun)
        )
        return result.scalar_one_or_none()

    def add(self, agent_run: AgentRun) -> None:
        self._session.add(agent_run)
