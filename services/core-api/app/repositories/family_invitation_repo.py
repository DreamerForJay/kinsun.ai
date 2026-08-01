"""Tenant-safe persistence for one-time family invitations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family_invitation import FamilyInvitation


class FamilyInvitationRepository:
    """Read and lock invitation rows without trusting caller-supplied scope."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, invitation: FamilyInvitation) -> None:
        self._session.add(invitation)

    async def get_by_token_hash_for_update(self, token_hash: str) -> FamilyInvitation | None:
        """Lock a code match globally; tenant scope comes only from the matched row."""
        result = await self._session.execute(
            select(FamilyInvitation)
            .where(FamilyInvitation.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_for_elder(
        self,
        *,
        invitation_id: UUID,
        tenant_id: UUID,
        elder_id: UUID,
        for_update: bool = False,
    ) -> FamilyInvitation | None:
        statement = select(FamilyInvitation).where(
            FamilyInvitation.id == invitation_id,
            FamilyInvitation.tenant_id == tenant_id,
            FamilyInvitation.elder_id == elder_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_elder(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
    ) -> list[FamilyInvitation]:
        result = await self._session.execute(
            select(FamilyInvitation)
            .where(
                FamilyInvitation.tenant_id == tenant_id,
                FamilyInvitation.elder_id == elder_id,
            )
            .order_by(FamilyInvitation.created_at.desc(), FamilyInvitation.id.desc())
        )
        return list(result.scalars().all())
