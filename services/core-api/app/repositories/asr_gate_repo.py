"""Tenant-scoped repository for the single ASR gate evidence row."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.asr_gate import AsrGateEvidence
from app.repositories.base import BaseRepository


class AsrGateRepository(BaseRepository):
    async def get_for_session_for_update(self, session_id: UUID) -> AsrGateEvidence | None:
        result = await self._session.execute(
            select(AsrGateEvidence)
            .where(
                AsrGateEvidence.session_id == session_id,
                AsrGateEvidence.tenant_id == self._tenant_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    def add(self, evidence: AsrGateEvidence) -> None:
        self._session.add(evidence)
