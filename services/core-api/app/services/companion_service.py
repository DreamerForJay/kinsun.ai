"""Authorized single-turn bridge from Core to the private Agent Runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.agent_runtime import AgentRuntimeClient
from app.core.exceptions import ConflictError, ServiceUnavailableError
from app.middleware.auth import ActorContext
from app.models.agent import AgentRun
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.safety import SafetyEvaluation
from app.schemas.conversation import CompanionTurnResponse
from app.services.conversation_service import ConversationService

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
        if conversation.state != "CREATED":
            raise ConflictError("Companion turn requires a newly created session")
        if not conversation.policy_version:
            raise ConflictError("Voice session has no policy version")

        request_id = f"req-{uuid4()}"
        request_payload: dict[str, object] = {
            "schema_version": "1.0.0",
            "request_id": request_id,
            "trace_id": conversation.trace_id,
            "session_id": str(conversation.id),
            "actor_id": str(actor_context.actor_id),
            "actor_role": _ACTOR_ROLE_MAP.get(actor_context.actor_role, "staff"),
            "elder_id": str(conversation.elder_id),
            "tenant_id": str(actor_context.tenant_id),
            "purpose": "BASIC_VOICE",
            "consent_version": str(conversation.consent_version),
            "policy_version": conversation.policy_version,
            "language": _LANGUAGE_MAP[conversation.language_route],
            "input_text": input_text,
            "allowed_tools": [],
            "max_steps": 3,
            "latency_budget_ms": latency_budget_ms,
        }

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
        started_clock = perf_counter()
        runtime_result = await self._runtime_client.run(
            request_payload=request_payload,
            correlation_id=correlation_id,
        )
        latency_ms = max(0, round((perf_counter() - started_clock) * 1000))

        if (
            runtime_result.request_id != request_id
            or runtime_result.trace_id != conversation.trace_id
        ):
            raise ServiceUnavailableError("Agent runtime response correlation mismatch")

        await self._conversations.transition(
            conversation=conversation,
            target_state="RESPONDING",
            actor_id=actor_context.actor_id,
            trace_id=correlation_id,
            idempotency_key=idempotency_key,
        )

        agent_run_id = _runtime_uuid(runtime_result.agent_run_id, "run-")
        agent_run = AgentRun(
            agent_run_id=agent_run_id,
            session_id=conversation.id,
            elder_id=conversation.elder_id,
            tenant_id=self._tenant_id,
            actor_id=actor_context.actor_id,
            agent_id=runtime_result.selected_agent,
            agent_version=runtime_result.schema_version,
            result_status=_RESULT_STATUS_MAP[runtime_result.result_status],
            model_id=self._model_route,
            prompt_version="m0-companion-v1",
            policy_version=conversation.policy_version,
            latency_ms=latency_ms,
            token_usage={},
            stop_reason=",".join(runtime_result.reason_codes)[:160] or None,
            trace_id=runtime_result.trace_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        self._session.add(agent_run)

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
