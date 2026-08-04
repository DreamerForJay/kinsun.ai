"""Purpose-based consent application service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.domain.state_machine import require_session_transition
from app.events.outbox_writer import write_outbox_entry
from app.models.consent import ConsentGrant
from app.repositories.consent_repo import ConsentRepository
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.policy_repo import PolicyRepository
from app.schemas.consent import (
    ConsentPurpose,
    CreateConsentRequest,
    RevokeConsentRequest,
)
from app.services.deletion_service import DeletionService

CAPABILITIES: dict[str, list[str]] = {
    ConsentPurpose.BASIC_VOICE.value: ["voice_session"],
    ConsentPurpose.TRANSCRIPT_STORAGE.value: ["transcript_storage"],
    ConsentPurpose.CARE_EVENT_EXTRACTION.value: ["care_event_candidate"],
    ConsentPurpose.LONG_TERM_MEMORY.value: ["memory_candidate", "confirmed_memory"],
    ConsentPurpose.COMPANION_SIGNAL_ANALYSIS.value: ["companion_signal_analysis"],
    ConsentPurpose.PROACTIVE_COMPANION.value: ["proactive_companion"],
    ConsentPurpose.FAMILY_SHARING.value: ["family_report", "family_notification"],
}


class ConsentService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._consents = ConsentRepository(session, tenant_id)
        self._policies = PolicyRepository(session, tenant_id)

    async def list_for_elder(self, elder_id: UUID) -> list[ConsentGrant]:
        return await self._consents.list_for_elder(elder_id)

    async def get_by_id(self, elder_id: UUID, consent_id: UUID) -> ConsentGrant | None:
        return await self._consents.get_by_id(elder_id, consent_id)

    async def _cancel_active_basic_voice_sessions(
        self,
        consent: ConsentGrant,
        now: datetime,
    ) -> None:
        if consent.purpose_code != ConsentPurpose.BASIC_VOICE.value:
            return
        conversations = await ConversationRepository(
            self._session,
            self._tenant_id,
        ).list_active_for_consent_for_update(consent.id)
        for conversation in conversations:
            require_session_transition(conversation.state, "CANCELLED")
            conversation.state = "CANCELLED"
            conversation.ended_at = now

    async def require_active(
        self,
        *,
        elder_id: UUID,
        purpose: ConsentPurpose | str,
        current_time: datetime | None = None,
    ) -> ConsentGrant:
        purpose_code = purpose.value if isinstance(purpose, ConsentPurpose) else purpose
        consent = await self._consents.get_active(
            elder_id=elder_id,
            purpose_code=purpose_code,
            current_time=current_time or datetime.now(UTC),
        )
        if consent is None:
            raise NotFoundError("Required consent is not active")
        return consent

    async def create_grants(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        request: CreateConsentRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> list[ConsentGrant]:
        now = datetime.now(UTC)
        policy = await self._policies.find_active_consent_policy(
            version=request.policy_version,
            current_time=now,
        )
        if policy is None:
            raise NotFoundError("Active consent policy not found")

        created: list[ConsentGrant] = []
        for purpose in request.purposes:
            active = await self._consents.get_active(
                elder_id=elder_id,
                purpose_code=purpose.value,
                current_time=now,
            )
            if active is not None:
                active.status = "REVOKED"
                active.revoked_at = now
                await self._cancel_active_basic_voice_sessions(active, now)
                await self._session.flush()
                await write_outbox_entry(
                    self._session,
                    event_type="consent.revoked.v1",
                    aggregate_type="consent_grant",
                    aggregate_id=active.id,
                    aggregate_version=active.version,
                    tenant_id=self._tenant_id,
                    elder_id=elder_id,
                    actor_id=actor_id,
                    purpose=active.purpose_code,
                    consent_version=active.version,
                    payload={
                        "consent_id": str(active.id),
                        "purpose_code": active.purpose_code,
                        "status": "REVOKED",
                        "reason_code": "SUPERSEDED_BY_NEW_GRANT",
                        "request_deletion": False,
                    },
                    trace_id=trace_id,
                    correlation_id=trace_id,
                    idempotency_key=idempotency_key,
                )

            version = await self._consents.next_version(elder_id, purpose.value)
            grant = ConsentGrant(
                elder_id=elder_id,
                purpose_code=purpose.value,
                status="GRANTED",
                version=version,
                scope={"share_scopes": request.share_scopes},
                granted_by_actor_id=actor_id,
                policy_id=policy.id,
                granted_at=now,
                effective_at=request.effective_at or now,
                expires_at=request.expires_at,
            )
            self._consents.add(grant)
            await self._session.flush()
            await write_outbox_entry(
                self._session,
                event_type="consent.granted.v1",
                aggregate_type="consent_grant",
                aggregate_id=grant.id,
                aggregate_version=grant.version,
                tenant_id=self._tenant_id,
                elder_id=elder_id,
                actor_id=actor_id,
                purpose=purpose.value,
                consent_version=grant.version,
                payload={
                    "consent_id": str(grant.id),
                    "purpose_code": purpose.value,
                    "status": grant.status,
                },
                trace_id=trace_id,
                correlation_id=trace_id,
                idempotency_key=idempotency_key,
            )
            created.append(grant)
        return created

    async def revoke(
        self,
        *,
        elder_id: UUID,
        consent_id: UUID,
        actor_id: UUID,
        request: RevokeConsentRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> tuple[ConsentGrant, UUID | None]:
        consent = await self._consents.get_by_id(elder_id, consent_id)
        if consent is None:
            raise NotFoundError("Resource not found")
        if consent.status != "GRANTED":
            raise ConflictError("Only a GRANTED consent can be revoked")

        now = datetime.now(UTC)
        effective_at = request.requested_effective_at or now
        if effective_at > now:
            raise ConflictError("Consent revocation cannot be scheduled in the future")

        consent.status = "REVOKED"
        consent.revoked_at = effective_at
        await self._cancel_active_basic_voice_sessions(consent, now)
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="consent.revoked.v1",
            aggregate_type="consent_grant",
            aggregate_id=consent.id,
            aggregate_version=consent.version,
            tenant_id=self._tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose=consent.purpose_code,
            consent_version=consent.version,
            payload={
                "consent_id": str(consent.id),
                "purpose_code": consent.purpose_code,
                "status": "REVOKED",
                "reason_code": request.reason_code,
                "request_deletion": request.request_deletion,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        deletion_request_id = None
        if request.request_deletion:
            deletion_request = await DeletionService(
                self._session,
                self._tenant_id,
            ).create_for_revocation(
                consent=consent,
                actor_id=actor_id,
                requested_scope=request.revoke_scope,
                reason_code=request.reason_code,
                effective_at=effective_at,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
            )
            deletion_request_id = deletion_request.id
        return consent, deletion_request_id
