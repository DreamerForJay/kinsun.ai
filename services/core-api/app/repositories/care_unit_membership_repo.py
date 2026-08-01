"""CareUnitMembershipRepository — queries care unit membership records.

This repository does NOT extend BaseRepository because membership
is not a tenant-scoped entity itself — it IS the association between
actors and care units. It takes a session directly.

Reads eldercare_ai.actor_tenant_membership, the same table
TenantMembershipRepository uses, filtered to rows that name a care unit.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import ActorTenantMembership


class CareUnitMembershipRepository:
    """Repository for care-unit-level membership lookups.

    Takes session only (no tenant_id in constructor) — tenant_id is
    passed explicitly per query method.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_member(
        self,
        actor_id: UUID,
        care_unit_id: UUID,
        tenant_id: UUID,
        role_code: str,
        current_time: datetime,
    ) -> bool:
        """Check active care-unit membership for a tenant-local acting role.

        tenant_id and role_code are required: omitting either would allow a
        membership from another tenant or role to satisfy this authorization
        boundary.

        Args:
            actor_id: The actor's UUID.
            care_unit_id: The care unit's UUID.
            tenant_id: The tenant the care unit must belong to.
            role_code: The tenant-local role being exercised.
            current_time: Trusted server time used for the effective window.

        Returns:
            True if a matching active membership exists, False otherwise.
        """
        result = await self._session.execute(
            select(ActorTenantMembership.id)
            .where(
                ActorTenantMembership.actor_id == actor_id,
                ActorTenantMembership.care_unit_id == care_unit_id,
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
        return result.scalar_one_or_none() is not None

    async def get_care_unit_ids(
        self,
        actor_id: UUID,
        tenant_id: UUID,
        role_code: str,
        current_time: datetime,
    ) -> list[UUID]:
        """Return active care-unit IDs for a tenant-local acting role.

        Rows with a NULL care_unit_id are tenant-wide memberships and are
        excluded — they name no specific care unit.

        Args:
            actor_id: The actor's UUID.
            tenant_id: The tenant's UUID.
            role_code: The tenant-local role being exercised.
            current_time: Trusted server time used for the effective window.

        Returns:
            Care-unit UUIDs for matching active memberships in the tenant.
        """
        result = await self._session.execute(
            select(ActorTenantMembership.care_unit_id).where(
                ActorTenantMembership.actor_id == actor_id,
                ActorTenantMembership.tenant_id == tenant_id,
                ActorTenantMembership.role_code == role_code,
                ActorTenantMembership.care_unit_id.is_not(None),
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= current_time,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    current_time < ActorTenantMembership.effective_to,
                ),
            )
        )
        return list(result.scalars().all())
