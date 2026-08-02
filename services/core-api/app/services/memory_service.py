"""Memory candidate, confirmation, correction, and deletion lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationDeniedError, ConflictError, ValidationError
from app.domain.state_machine import require_memory_transition
from app.events.outbox_writer import write_outbox_entry
from app.middleware.auth import ActorContext
from app.models.care_event import CareEvent
from app.models.enums import ActorType
from app.models.memory import Memory, MemoryVersion
from app.repositories.memory_repo import MemoryRepository
from app.schemas.consent import ConsentPurpose
from app.schemas.memory import (
    ConfirmMemoryRequest,
    CreateMemoryCandidateRequest,
    UpdateMemoryRequest,
)
from app.services.consent_service import ConsentService


class MemoryService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._memories = MemoryRepository(session, tenant_id)

    async def get(self, elder_id: UUID, memory_id: UUID) -> Memory | None:
        return await self._memories.get(elder_id, memory_id)

    async def get_version(self, memory: Memory) -> MemoryVersion:
        return await self._memories.get_current_version(memory)

    async def list_for_elder(self, **kwargs) -> list[Memory]:
        return await self._memories.list_for_elder(**kwargs)

    async def create_candidate(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        request: CreateMemoryCandidateRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.LONG_TERM_MEMORY,
        )
        count = await self._session.scalar(
            select(func.count())
            .select_from(CareEvent)
            .where(
                CareEvent.id.in_(request.source_event_ids),
                CareEvent.elder_id == elder_id,
                CareEvent.tenant_id == self._tenant_id,
                CareEvent.status.in_(["VERIFIED", "CORRECTED"]),
            )
        )
        if count != len(set(request.source_event_ids)):
            raise ValidationError(
                details=[
                    {
                        "field": "source_event_ids",
                        "reason": "every source must be a verified event for this elder",
                    }
                ]
            )

        memory = Memory(
            elder_id=elder_id,
            tenant_id=self._tenant_id,
            memory_type=request.memory_type.value,
            status="CANDIDATE",
            current_version=1,
            consent_version=consent.version,
        )
        self._memories.add_memory(memory)
        await self._session.flush()
        self._memories.add_version(
            MemoryVersion(
                memory_id=memory.id,
                version=1,
                content=request.normalized_content,
                source_event_ids=request.source_event_ids,
                version_status="ACTIVE",
                created_by_actor_id=actor_id,
            )
        )
        await self._session.flush()
        await self._write_event(
            event_type="memory.candidate-created.v1",
            memory=memory,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def confirm(
        self,
        *,
        memory: Memory,
        actor_context: ActorContext,
        request: ConfirmMemoryRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        """Promote a candidate only after the authenticated elder confirms it.

        ``ELDER_UI`` is an explicit Core command made by the elder self. Core
        derives the actor and elder relationship from trusted server-side
        context and generates an opaque evidence reference from the request
        trace. Caregiver and legal-representative review may help prepare a
        candidate, but cannot satisfy the elder confirmation gate.

        VOICE confirmation remains unavailable until a versioned,
        consent-scoped record can prove an affirmative answer to this exact
        candidate. A completed conversation alone is insufficient.
        """
        if memory.current_version != request.expected_candidate_version:
            raise ConflictError("Memory candidate version conflict")
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=memory.elder_id,
            purpose=ConsentPurpose.LONG_TERM_MEMORY,
        )
        if consent.version != request.consent_version or consent.version != memory.consent_version:
            raise ConflictError("Consent version changed; create a new candidate confirmation")

        await self._validate_confirmation_authority(
            memory=memory,
            actor_context=actor_context,
            request=request,
        )

        require_memory_transition(memory.status, "CONFIRMED")
        now = datetime.now(UTC)
        memory.status = "CONFIRMED"
        memory.confirmed_by_actor_id = actor_context.actor_id
        memory.confirmed_at = now
        memory.confirmation_method = request.confirmation_method
        memory.confirmation_session_id = None
        memory.confirmation_evidence_ref = f"core-command:{trace_id}"
        require_memory_transition(memory.status, "ACTIVE")
        memory.status = "ACTIVE"
        memory.activated_at = now
        await self._session.flush()
        await self._write_event(
            event_type="memory.confirmed.v1",
            memory=memory,
            actor_id=actor_context.actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def _validate_confirmation_authority(
        self,
        *,
        memory: Memory,
        actor_context: ActorContext,
        request: ConfirmMemoryRequest,
    ) -> None:
        """Allow only an authenticated elder to confirm their own candidate."""
        if request.confirmation_method == "VOICE":
            raise ValidationError(
                details=[
                    {
                        "field": "confirmation_method",
                        "reason": (
                            "VOICE confirmation is unavailable until an affirmative "
                            "candidate-specific evidence record is implemented"
                        ),
                    }
                ]
            )

        if request.confirmation_method != "ELDER_UI" or actor_context.actor_role != ActorType.ELDER:
            raise AuthorizationDeniedError("Resource not found")

    async def set_candidate_state(
        self,
        *,
        memory: Memory,
        target: str,
        actor_id: UUID,
        expected_version: int,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        if memory.current_version != expected_version:
            raise ConflictError("Memory candidate version conflict")
        require_memory_transition(memory.status, target)
        memory.status = target
        await self._session.flush()
        await self._write_event(
            event_type=f"memory.{target.lower()}.v1",
            memory=memory,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def update(
        self,
        *,
        memory: Memory,
        actor_id: UUID,
        request: UpdateMemoryRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=memory.elder_id,
            purpose=ConsentPurpose.LONG_TERM_MEMORY,
        )
        if memory.status not in {"ACTIVE", "INACTIVE"}:
            raise ConflictError("Only active or inactive memory can be corrected")
        if memory.current_version != request.expected_version:
            raise ConflictError("Memory version conflict")
        current = await self._memories.get_current_version(memory)
        now = datetime.now(UTC)
        current.version_status = "INACTIVE"
        current.valid_to = now
        memory.current_version += 1
        self._memories.add_version(
            MemoryVersion(
                memory_id=memory.id,
                version=memory.current_version,
                content=request.content,
                source_event_ids=current.source_event_ids,
                version_status="ACTIVE",
                created_by_actor_id=actor_id,
                supersedes_version_id=current.memory_version_id,
            )
        )
        await self._session.flush()
        await self._write_event(
            event_type="memory.corrected.v1",
            memory=memory,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def delete(
        self,
        *,
        memory: Memory,
        actor_id: UUID,
        expected_version: int,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        if memory.current_version != expected_version:
            raise ConflictError("Memory version conflict")
        require_memory_transition(memory.status, "DELETED")
        now = datetime.now(UTC)
        memory.status = "DELETED"
        memory.deleted_at = now
        memory.deactivated_at = now
        current = await self._memories.get_current_version(memory)
        current.version_status = "DELETED"
        current.valid_to = now
        await self._session.flush()
        await self._write_event(
            event_type="memory.deleted.v1",
            memory=memory,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def _write_event(
        self,
        *,
        event_type: str,
        memory: Memory,
        actor_id: UUID,
        trace_id: str,
        idempotency_key: str,
    ) -> None:
        await write_outbox_entry(
            self._session,
            event_type=event_type,
            aggregate_type="memory",
            aggregate_id=memory.id,
            aggregate_version=memory.current_version,
            tenant_id=self._tenant_id,
            elder_id=memory.elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.LONG_TERM_MEMORY.value,
            consent_version=memory.consent_version,
            payload={
                "memory_id": str(memory.id),
                "status": memory.status,
                "version": memory.current_version,
                "confirmation_method": memory.confirmation_method,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
