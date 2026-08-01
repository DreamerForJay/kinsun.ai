"""Actor repository for trusted identity-profile lookups.

Actor is intentionally not tenant-scoped because one actor may belong to
multiple tenants.  Tenant membership is validated separately by
``TenantMembershipRepository`` before profile data is returned.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor


class ActorRepository:
    """Read formal actor state from the Core source of truth."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_by_id(self, actor_id: UUID) -> Actor | None:
        """Return an active actor by UUID, or ``None`` when unavailable."""
        result = await self._session.execute(
            select(Actor).where(
                Actor.id == actor_id,
                Actor.status == "ACTIVE",
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_cognito_sub(self, cognito_sub: str) -> Actor | None:
        """Return the one active Actor bound to a verified Cognito subject.

        The database unique constraint on ``actor.cognito_sub`` is the source
        of identity uniqueness.  Authentication callers must still fail closed
        if no active local actor has been provisioned.
        """
        result = await self._session.execute(
            select(Actor).where(
                Actor.cognito_sub == cognito_sub,
                Actor.status == "ACTIVE",
            )
        )
        return result.scalar_one_or_none()
