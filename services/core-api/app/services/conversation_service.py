"""Conversation-session lifecycle service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.domain.state_machine import require_session_transition
from app.events.outbox_writer import write_outbox_entry
from app.models.conversation import ConversationSession
from app.models.policy import PolicyRegistry
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.consent import ConsentPurpose
from app.schemas.conversation import CreateVoiceSessionRequest, CreateVoiceTicketRequest
from app.services.consent_service import ConsentService
from app.services.voice_ticket_codec import IssuedVoiceTicket, VoiceTicketCodec


class ConversationService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._repository = ConversationRepository(session, tenant_id)

    async def get(self, session_id: UUID) -> ConversationSession | None:
        return await self._repository.get_by_id(session_id)

    async def get_for_update(self, session_id: UUID) -> ConversationSession | None:
        """Lock and refresh the tenant-scoped session before a turn mutates it."""
        return await self._repository.get_by_id_for_update(session_id)

    async def create(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        actor_role: str,
        request: CreateVoiceSessionRequest | CreateVoiceTicketRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> ConversationSession:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.BASIC_VOICE,
        )
        policy = await self._session.get(PolicyRegistry, consent.policy_id)
        initiator_type = {
            "ELDER": "ELDER",
            "FAMILY_MEMBER": "FAMILY",
            "SYSTEM_SERVICE": "SYSTEM",
        }.get(actor_role, "CAREGIVER")
        conversation = ConversationSession(
            elder_id=elder_id,
            tenant_id=self._tenant_id,
            initiator_actor_id=actor_id,
            initiator_type=initiator_type,
            language_route=request.language_preference.value,
            state="CREATED",
            trace_id=trace_id,
            consent_id=consent.id,
            consent_version=consent.version,
            policy_version=policy.version if policy is not None else None,
        )
        self._repository.add(conversation)
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="conversation.session.created.v1",
            aggregate_type="conversation_session",
            aggregate_id=conversation.id,
            aggregate_version=1,
            tenant_id=self._tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.BASIC_VOICE.value,
            consent_version=consent.version,
            payload={
                "session_id": str(conversation.id),
                "state": conversation.state,
                "language_route": conversation.language_route,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return conversation

    async def issue_ticket(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        actor_role: str,
        request: CreateVoiceSessionRequest | CreateVoiceTicketRequest,
        trace_id: str,
        idempotency_key: str,
        codec: VoiceTicketCodec,
    ) -> tuple[ConversationSession, IssuedVoiceTicket]:
        conversation = await self.create(
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role=actor_role,
            request=request,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return conversation, codec.issue(conversation)

    async def replay_ticket(
        self,
        session_id: UUID,
        codec: VoiceTicketCodec,
    ) -> tuple[ConversationSession, IssuedVoiceTicket]:
        conversation = await self._repository.get_by_id(session_id)
        if conversation is None or conversation.state != "CREATED":
            raise AuthenticationError("Voice ticket is invalid or unavailable")
        await self._require_ticket_consent(conversation)
        return conversation, codec.issue(conversation)

    async def consume_ticket(
        self,
        *,
        session_id: UUID,
        value: str,
        actor_id: UUID,
        trace_id: str,
        codec: VoiceTicketCodec,
    ) -> ConversationSession:
        conversation = await self._repository.get_by_id_for_update(session_id)
        if conversation is None:
            raise AuthenticationError("Voice ticket is invalid or unavailable")
        codec.verify(value, conversation)
        if conversation.state != "CREATED":
            raise AuthenticationError("Voice ticket is invalid or unavailable")
        await self._require_ticket_consent(conversation)
        return await self.transition(
            conversation=conversation,
            target_state="RECORDING",
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=f"voice-ticket-consume:{conversation.id}",
        )

    async def _require_ticket_consent(
        self,
        conversation: ConversationSession,
    ) -> None:
        try:
            active_consent = await ConsentService(
                self._session,
                self._tenant_id,
            ).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.BASIC_VOICE,
            )
        except NotFoundError:
            raise AuthenticationError("Voice ticket is invalid or unavailable") from None
        if (
            active_consent.id != conversation.consent_id
            or active_consent.version != conversation.consent_version
        ):
            raise AuthenticationError("Voice ticket is invalid or unavailable")

    async def transition(
        self,
        *,
        conversation: ConversationSession,
        target_state: str,
        actor_id: UUID,
        trace_id: str,
        idempotency_key: str,
    ) -> ConversationSession:
        if target_state not in {"CANCELLED", "FAILED"}:
            active_consent = await ConsentService(
                self._session,
                self._tenant_id,
            ).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.BASIC_VOICE,
            )
            if (
                active_consent.id != conversation.consent_id
                or active_consent.version != conversation.consent_version
            ):
                raise ConflictError("Voice session consent version is no longer active")
        require_session_transition(conversation.state, target_state)
        conversation.state = target_state
        if target_state in {"COMPLETED", "CANCELLED", "FAILED"}:
            conversation.ended_at = datetime.now(UTC)
        await self._session.flush()
        if target_state == "COMPLETED":
            await write_outbox_entry(
                self._session,
                event_type="conversation.session.completed.v1",
                aggregate_type="conversation_session",
                aggregate_id=conversation.id,
                aggregate_version=1,
                tenant_id=self._tenant_id,
                elder_id=conversation.elder_id,
                actor_id=actor_id,
                purpose=ConsentPurpose.BASIC_VOICE.value,
                consent_version=conversation.consent_version,
                payload={
                    "session_id": str(conversation.id),
                    "state": target_state,
                },
                trace_id=trace_id,
                correlation_id=conversation.trace_id,
                idempotency_key=idempotency_key,
            )
        return conversation
