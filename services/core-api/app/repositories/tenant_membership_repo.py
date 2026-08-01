"""TenantMembershipRepository — queries tenant membership records.

This repository does NOT extend BaseRepository because membership
is not a tenant-scoped entity itself — it IS the association between
actors and tenants. It takes a session directly.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import ActorTenantMembership


class TenantMembershipRepository:
    """Repository for tenant-level membership lookups.

    Takes session only (no tenant_id in constructor) — tenant_id is
    passed explicitly per query method.

    Reads eldercare_ai.actor_tenant_membership, the same table
    CareUnitMembershipRepository uses. Rows scoped to a care unit still count
    as tenant membership, so this query does not filter on care_unit_id.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_membership(
        self,
        actor_id: UUID,
        tenant_id: UUID,
        role_code: str,
        current_time: datetime,
    ) -> ActorTenantMembership | None:
        """Return a currently effective membership for the tenant and acting role.

        An actor may legitimately hold several rows for one tenant — one
        tenant-wide plus one per care unit — so this returns the first match
        rather than requiring exactly one. The acting role is mandatory: a
        membership under another tenant-local role must never authorize the
        role asserted by the authentication context.

        Args:
            actor_id: The actor's UUID.
            tenant_id: The tenant's UUID.
            role_code: The tenant-local role being exercised.
            current_time: Trusted server time used for the effective window.

        Returns:
            A matching active ActorTenantMembership, or None.
        """
        result = await self._session.execute(
            select(ActorTenantMembership)
            .where(
                ActorTenantMembership.actor_id == actor_id,
                ActorTenantMembership.tenant_id == tenant_id,
                ActorTenantMembership.role_code == role_code,
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= current_time,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    current_time < ActorTenantMembership.effective_to,
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
