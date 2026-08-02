"""Authorized single-turn bridge from Core to the private Agent Runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.agent_runtime import AgentRuntimeClient
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.middleware.auth import ActorContext
from app.models.agent import AgentRun
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.safety import SafetyEvaluation
from app.schemas.care_event import CreateCareEventCandidateRequest
from app.schemas.consent import ConsentPurpose
from app.schemas.conversation import CompanionTurnResponse
from app.services.asr_gate_service import AsrGateService
from app.services.authorization_service import authorize_elder
from app.services.care_event_service import CareEventService
from app.services.consent_service import ConsentService
from app.services.conversation_service import ConversationService
from app.services.knowledge_intent import resolve_turn_purpose

_ACTOR_ROLE_MAP = {
    "ELDER": "elder",
    "FAMILY_MEMBER": "family",
    "SYSTEM_SERVICE": "system",
}

_LANGUAGE_MAP = {
    "ZH_TW": "zh-TW",
    "NAN_TW": "nan-TW",
    "HAK_TW": "hak-TW",
    "EN_US": "en-US",
    "MIXED": "zh-TW",
    "UNKNOWN": "zh-TW",
}

_RESULT_STATUS_MAP = {
    "SUCCESS": "SUCCESS",
    "BLOCKED": "BLOCKED",
    "SAFE_FALLBACK": "HUMAN_REVIEW",
    "FAILED": "DEPENDENCY_FAILED",
}

_SAFETY_DECISION_MAP = {
    "ALLOW": "ALLOW",
    "BLOCK": "BLOCK",
    "SAFE_FALLBACK": "HUMAN_REVIEW",
    "HUMAN_REVIEW": "HUMAN_REVIEW",
}


def _runtime_uuid(value: str, prefix: str) -> UUID:
    raw = value.removeprefix(prefix)
    try:
        return UUID(raw)
    except ValueError as exc:
        raise ServiceUnavailableError("Agent runtime returned an invalid identifier") from exc


class CompanionService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        runtime_client: AgentRuntimeClient,
        model_route: str,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._runtime_client = runtime_client
        self._model_route = model_route
        self._conversations = ConversationService(session, tenant_id)

    async def _requested_outputs(
        self,
        *,
        conversation: ConversationSession,
        actor_context: ActorContext,
    ) -> list[str]:
        """Derive proposal scope from current Core authorization and consent."""
        try:
            await authorize_elder(
                self._session,
                actor_context,
                conversation.elder_id,
                "care_event:candidate:create",
            )
            await ConsentService(self._session, self._tenant_id).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
            )
        except NotFoundError:
            return []
        return ["event_candidate"]

    async def _authorize_asr_input(
        self,
        *,
        conversation: ConversationSession,
        input_text: str,
    ) -> None:
        settings = get_settings()
        if not settings.asr_gate_enabled:
            raise AuthenticationError("ASR input is unavailable")
        await AsrGateService(
            self._session,
            self._tenant_id,
            digest_secret=settings.asr_gate_hmac_secret,
            confidence_threshold=settings.asr_gate_confidence_threshold,
            evidence_ttl_seconds=settings.asr_gate_evidence_ttl_seconds,
        ).authorize_agent_input(
            conversation=conversation,
            input_text=input_text,
        )

    async def run_turn(
        self,
        *,
        conversation: ConversationSession,
        actor_context: ActorContext,
        input_text: str,
        correlation_id: str,
        idempotency_key: str,
        latency_budget_ms: int,
    ) -> CompanionTurnResponse:
        supplied_elder_id = conversation.elder_id
        conversation = await self._conversations.get_for_update(conversation.id)
        if conversation is None or conversation.elder_id != supplied_elder_id:
            raise NotFoundError("Resource not found")

        initial_state = conversation.state
        if initial_state not in {"CREATED", "PROCESSING"}:
            raise ConflictError("Companion turn is not ready for Agent Runtime")
        if not conversation.policy_version:
            raise ConflictError("Voice session has no policy version")
        if initial_state == "PROCESSING":
            await self._authorize_asr_input(
                conversation=conversation,
                input_text=input_text,
            )

        request_id = f"req-{uuid4()}"
        agent_run_id = uuid4()
        agent_run_wire_id = f"run-{agent_run_id}"
        requested_outputs = await self._requested_outputs(
            conversation=conversation,
            actor_context=actor_context,
        )
        # The Agent Runtime selects a retrieval profile from `purpose`
        # (rag_integration.RAG_PURPOSES) and does not infer intent itself, so an
        # information request has to be identified here or the knowledge base is
        # never consulted. Everyday conversation keeps BASIC_VOICE.
        turn_purpose = resolve_turn_purpose(input_text)
        request_payload: dict[str, object] = {
            "schema_version": "1.0.0",
            "request_id": request_id,
            "trace_id": conversation.trace_id,
            "agent_run_id": agent_run_wire_id,
            "session_id": str(conversation.id),
            "actor_id": str(actor_context.actor_id),
            "actor_role": _ACTOR_ROLE_MAP.get(actor_context.actor_role, "staff"),
            "elder_id": str(conversation.elder_id),
            "tenant_id": str(actor_context.tenant_id),
            "purpose": turn_purpose,
            "consent_version": str(conversation.consent_version),
            "policy_version": conversation.policy_version,
            "language": _LANGUAGE_MAP[conversation.language_route],
            "input_text": input_text,
            "allowed_tools": [],
            "requested_outputs": requested_outputs,
            "max_steps": 3,
            "latency_budget_ms": latency_budget_ms,
        }

        if initial_state == "CREATED":
            await self._conversations.transition(
                conversation=conversation,
                target_state="RECORDING",
                actor_id=actor_context.actor_id,
                trace_id=correlation_id,
                idempotency_key=idempotency_key,
            )
            await self._conversations.transition(
                conversation=conversation,
                target_state="PROCESSING",
                actor_id=actor_context.actor_id,
                trace_id=correlation_id,
                idempotency_key=idempotency_key,
            )

        started_at = datetime.now(UTC)
        agent_run = AgentRun(
            agent_run_id=agent_run_id,
            session_id=conversation.id,
            elder_id=conversation.elder_id,
            tenant_id=self._tenant_id,
            actor_id=actor_context.actor_id,
            agent_id="companion-agent",
            agent_version="1.0.0",
            result_status="RUNNING",
            model_id=self._model_route,
            prompt_version="m0-companion-v1",
            policy_version=conversation.policy_version,
            token_usage={},
            trace_id=conversation.trace_id,
            started_at=started_at,
        )
        self._session.add(agent_run)
        await self._session.flush()

        started_clock = perf_counter()
        runtime_result = await self._runtime_client.run(
            request_payload=request_payload,
            correlation_id=correlation_id,
        )
        latency_ms = max(0, round((perf_counter() - started_clock) * 1000))

        if (
            runtime_result.request_id != request_id
            or runtime_result.trace_id != conversation.trace_id
            or runtime_result.agent_run_id != agent_run_wire_id
        ):
            raise ServiceUnavailableError("Agent runtime response correlation mismatch")

        await self._conversations.transition(
            conversation=conversation,
            target_state="RESPONDING",
            actor_id=actor_context.actor_id,
            trace_id=correlation_id,
            idempotency_key=idempotency_key,
        )

        if _runtime_uuid(runtime_result.agent_run_id, "run-") != agent_run_id:
            raise ServiceUnavailableError("Agent runtime response correlation mismatch")
        agent_run.agent_id = runtime_result.selected_agent
        agent_run.agent_version = runtime_result.schema_version
        agent_run.result_status = _RESULT_STATUS_MAP[runtime_result.result_status]
        agent_run.latency_ms = latency_ms
        agent_run.stop_reason = ",".join(runtime_result.reason_codes)[:160] or None
        agent_run.completed_at = datetime.now(UTC)

        consent = await self._session.get(ConsentGrant, conversation.consent_id)
        if consent is None:
            raise ServiceUnavailableError("Voice session consent snapshot is unavailable")
        self._session.add(
            SafetyEvaluation(
                agent_run_id=agent_run_id,
                policy_id=consent.policy_id,
                target_type="agent_output",
                target_id=conversation.id,
                decision=_SAFETY_DECISION_MAP[runtime_result.safety_result.decision],
                reason_codes=runtime_result.safety_result.reason_codes,
                flags={"risk_level": runtime_result.safety_result.risk_level},
            )
        )
        await self._session.flush()

        await self._conversations.transition(
            conversation=conversation,
            target_state="COMPLETED",
            actor_id=actor_context.actor_id,
            trace_id=correlation_id,
            idempotency_key=idempotency_key,
        )

        proposal = runtime_result.event_candidate_proposal
        if (
            proposal is not None
            and "event_candidate" in requested_outputs
            and runtime_result.result_status == "SUCCESS"
            and runtime_result.safety_result.decision == "ALLOW"
        ):
            try:
                await authorize_elder(
                    self._session,
                    actor_context,
                    conversation.elder_id,
                    "care_event:candidate:create",
                )
            except NotFoundError:
                pass
            else:
                # CareEventService rechecks the live extraction consent and
                # validates the completed Core-owned source session.
                await CareEventService(self._session, self._tenant_id).create_candidate(
                    elder_id=conversation.elder_id,
                    actor_id=actor_context.actor_id,
                    request=CreateCareEventCandidateRequest(
                        source_type="CONVERSATION_SESSION",
                        source_id=conversation.id,
                        source_version=1,
                        event_type=proposal.event_type,
                        event_time=proposal.event_time,
                        structured_payload=proposal.structured_payload,
                        evidence_refs=proposal.evidence_refs,
                        confidence_band=proposal.confidence_band,
                        review_requirement=proposal.review_requirement,
                        extractor_version=proposal.extractor_version,
                    ),
                    trace_id=correlation_id,
                    idempotency_key=f"event-candidate:{agent_run_id}",
                )

        return CompanionTurnResponse(
            session_id=conversation.id,
            agent_run_id=agent_run_id,
            trace_id=runtime_result.trace_id,
            context_manifest_id=runtime_result.context_manifest_id,
            reply_text=runtime_result.reply_text,
            reply_language=runtime_result.reply_language,
            result_status=runtime_result.result_status,
            safety_decision=runtime_result.safety_result.decision,
            risk_level=runtime_result.safety_result.risk_level,
            reason_codes=runtime_result.reason_codes,
            model_route=self._model_route,
        )
