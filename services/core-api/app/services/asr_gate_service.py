"""Consent- and state-gated ASR evidence handling."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.domain.state_machine import require_session_transition
from app.models.asr_gate import AsrGateEvidence
from app.models.elder import Elder
from app.repositories.asr_gate_repo import AsrGateRepository
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.asr_gate import AsrGateDecisionResponse, SubmitAsrResultRequest
from app.schemas.consent import ConsentPurpose
from app.services.consent_service import ConsentService


class AsrGateService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        digest_secret: str,
        confidence_threshold: float,
        evidence_ttl_seconds: int,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._repo = AsrGateRepository(session, tenant_id)
        self._conversations = ConversationRepository(session, tenant_id)
        self._digest_secret = digest_secret.encode("utf-8")
        self._threshold = confidence_threshold
        self._ttl = timedelta(seconds=evidence_ttl_seconds)

    def _digest(self, transcript: str) -> str:
        return hmac.new(self._digest_secret, transcript.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _decision(evidence: AsrGateEvidence) -> AsrGateDecisionResponse:
        decision = {
            "ALLOWED": "CAN_SEND_TO_AGENT",
            "CONFIRMED": "CAN_SEND_TO_AGENT",
            "AWAITING_CONFIRMATION": "CONFIRMATION_REQUIRED",
            "REJECTED": "CANNOT_SEND_TO_AGENT",
        }[evidence.gate_status]
        return AsrGateDecisionResponse(
            session_id=evidence.session_id,
            decision=decision,
            confirmation_required=decision == "CONFIRMATION_REQUIRED",
            expires_at=evidence.expires_at,
        )

    async def _require_live_voice_consent(self, conversation) -> None:
        try:
            consent = await ConsentService(self._session, self._tenant_id).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.BASIC_VOICE,
            )
        except NotFoundError:
            raise AuthenticationError("ASR result is unavailable") from None
        if consent.id != conversation.consent_id or consent.version != conversation.consent_version:
            raise AuthenticationError("ASR result is unavailable")

    async def submit(
        self, *, request: SubmitAsrResultRequest, actor_id: UUID
    ) -> AsrGateDecisionResponse:
        conversation = await self._conversations.get_by_id_for_update(request.session_id)
        if conversation is None:
            raise AuthenticationError("ASR result is unavailable")
        if conversation.language_route != request.language_route.value:
            raise AuthenticationError("ASR result is unavailable")
        await self._require_live_voice_consent(conversation)
        existing = await self._repo.get_for_session_for_update(request.session_id)
        if existing is not None:
            return self._decision(existing)
        if conversation.state != "RECORDING":
            raise AuthenticationError("ASR result is unavailable")
        now = datetime.now(UTC)
        transcript_storage_allowed = await self._has_transcript_consent(
            conversation.elder_id,
            now,
        )
        gate_status = (
            "ALLOWED" if request.confidence >= self._threshold else "AWAITING_CONFIRMATION"
        )
        target = "PROCESSING" if gate_status == "ALLOWED" else "AWAITING_CONFIRMATION"
        require_session_transition(conversation.state, target)
        conversation.state = target
        evidence = AsrGateEvidence(
            tenant_id=self._tenant_id,
            session_id=conversation.id,
            elder_id=conversation.elder_id,
            language_route=request.language_route.value,
            asr_model_version=request.asr_model_version,
            confidence=request.confidence,
            gate_status=gate_status,
            transcript_digest=self._digest(request.transcript),
            transcript=request.transcript if transcript_storage_allowed else None,
            expires_at=now + self._ttl,
        )
        self._repo.add(evidence)
        await self._session.flush()
        return self._decision(evidence)

    async def _has_transcript_consent(self, elder_id: UUID, now: datetime) -> bool:
        try:
            await ConsentService(self._session, self._tenant_id).require_active(
                elder_id=elder_id,
                purpose=ConsentPurpose.TRANSCRIPT_STORAGE,
                current_time=now,
            )
        except NotFoundError:
            return False
        return True

    async def authorize_agent_input(self, *, conversation, input_text: str) -> None:
        """Bind a PROCESSING turn to the exact transcript that passed the ASR gate."""
        if conversation.state != "PROCESSING":
            raise AuthenticationError("ASR input is unavailable")
        await self._require_live_voice_consent(conversation)
        evidence = await self._repo.get_for_session_for_update(conversation.id)
        now = datetime.now(UTC)
        if (
            evidence is None
            or evidence.elder_id != conversation.elder_id
            or evidence.gate_status not in {"ALLOWED", "CONFIRMED"}
            or (evidence.gate_status == "CONFIRMED" and evidence.confirmation_action != "CONFIRM")
            or evidence.expires_at <= now
            or not hmac.compare_digest(
                evidence.transcript_digest,
                self._digest(input_text),
            )
        ):
            raise AuthenticationError("ASR input is unavailable")

    async def confirm(
        self, *, session_id: UUID, actor_id: UUID, action: str
    ) -> AsrGateDecisionResponse:
        conversation = await self._conversations.get_by_id_for_update(session_id)
        evidence = await self._repo.get_for_session_for_update(session_id)
        if conversation is None or evidence is None:
            raise NotFoundError("Resource not found")
        elder = await self._session.get(Elder, conversation.elder_id)
        if elder is None or elder.actor_id != actor_id:
            raise NotFoundError("Resource not found")
        await self._require_live_voice_consent(conversation)
        now = datetime.now(UTC)
        if evidence.gate_status in {"CONFIRMED", "REJECTED"}:
            if (
                evidence.confirmed_by_actor_id == actor_id
                and evidence.confirmation_action == action
            ):
                return self._decision(evidence)
            raise ConflictError("ASR gate is already decided")
        if evidence.gate_status != "AWAITING_CONFIRMATION" or evidence.expires_at <= now:
            raise ConflictError("ASR gate confirmation is unavailable")
        target = "PROCESSING" if action == "CONFIRM" else "CANCELLED"
        require_session_transition(conversation.state, target)
        conversation.state = target
        if target == "CANCELLED":
            conversation.ended_at = now
        evidence.gate_status = "CONFIRMED" if action == "CONFIRM" else "REJECTED"
        evidence.confirmation_action = action
        evidence.confirmed_by_actor_id = actor_id
        evidence.confirmed_at = now
        await self._session.flush()
        return self._decision(evidence)
