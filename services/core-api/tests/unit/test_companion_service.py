"""Core-authorized companion bridge tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from app.adapters.agent_runtime import AgentRunResult, AgentSafetyResult
from app.core.exceptions import ServiceUnavailableError
from app.middleware.auth import ActorContext
from app.models.agent import AgentRun
from app.models.safety import SafetyEvaluation
from app.services import companion_service
from app.services.companion_service import CompanionService


def _runtime_result(*, request_id: str, trace_id: str) -> AgentRunResult:
    return AgentRunResult(
        schema_version="1.0.0",
        request_id=request_id,
        trace_id=trace_id,
        agent_run_id=f"run-{uuid4()}",
        selected_agent="companion-agent",
        reply_text="謝謝您和我分享。",
        reply_language="zh-TW",
        safety_result=AgentSafetyResult(
            schema_version="1.0.0",
            decision="ALLOW",
            risk_level="LOW",
            reason_codes=["ALLOW"],
            matched_terms=[],
            safe_reply=None,
        ),
        context_manifest_id="context-1",
        step_count=1,
        result_status="SUCCESS",
        reason_codes=["ALLOW"],
    )


@pytest.mark.asyncio
async def test_run_turn_uses_trusted_core_scope_and_persists_metadata_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = ActorContext(actor_id=uuid4(), actor_role="ELDER", tenant_id=tenant_id)
    conversation = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        consent_id=uuid4(),
        consent_version=2,
        policy_version="policy-v2",
        language_route="ZH_TW",
        state="CREATED",
        trace_id="trace-core-1",
    )
    transition = AsyncMock(return_value=conversation)
    monkeypatch.setattr(
        companion_service,
        "ConversationService",
        MagicMock(return_value=SimpleNamespace(transition=transition)),
    )
    runtime = SimpleNamespace(run=AsyncMock())

    async def run_runtime(*, request_payload, correlation_id):
        assert request_payload["actor_id"] == str(actor.actor_id)
        assert request_payload["tenant_id"] == str(tenant_id)
        assert request_payload["elder_id"] == str(conversation.elder_id)
        assert request_payload["allowed_tools"] == []
        assert correlation_id == "correlation-1"
        return _runtime_result(
            request_id=request_payload["request_id"],
            trace_id=conversation.trace_id,
        )

    runtime.run.side_effect = run_runtime
    session = MagicMock()
    session.get = AsyncMock(return_value=SimpleNamespace(policy_id=uuid4()))
    session.flush = AsyncMock()

    result = await CompanionService(
        session,
        tenant_id,
        runtime,
        "mock",
    ).run_turn(
        conversation=conversation,
        actor_context=actor,
        input_text="這是合成的早餐分享。",
        correlation_id="correlation-1",
        idempotency_key="turn-1",
        latency_budget_ms=3000,
    )

    assert result.session_state == "COMPLETED"
    assert result.transport_status == "TEXT_ONLY"
    assert result.reply_text == "謝謝您和我分享。"
    assert [item.kwargs["target_state"] for item in transition.await_args_list] == [
        "RECORDING",
        "PROCESSING",
        "RESPONDING",
        "COMPLETED",
    ]
    added = [item.args[0] for item in session.add.call_args_list]
    assert any(isinstance(item, AgentRun) for item in added)
    assert any(isinstance(item, SafetyEvaluation) for item in added)
    assert all("早餐分享" not in repr(item) for item in added)


@pytest.mark.asyncio
async def test_runtime_failure_does_not_create_agent_audit_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = ActorContext(actor_id=uuid4(), actor_role="ELDER", tenant_id=tenant_id)
    conversation = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        consent_id=uuid4(),
        consent_version=1,
        policy_version="policy-v1",
        language_route="ZH_TW",
        state="CREATED",
        trace_id="trace-core-1",
    )
    transition = AsyncMock(return_value=conversation)
    monkeypatch.setattr(
        companion_service,
        "ConversationService",
        MagicMock(return_value=SimpleNamespace(transition=transition)),
    )
    runtime = SimpleNamespace(
        run=AsyncMock(side_effect=ServiceUnavailableError("Agent runtime is unavailable"))
    )
    session = MagicMock()

    with pytest.raises(ServiceUnavailableError):
        await CompanionService(session, tenant_id, runtime, "mock").run_turn(
            conversation=conversation,
            actor_context=actor,
            input_text="合成測試文字",
            correlation_id="correlation-1",
            idempotency_key="turn-1",
            latency_budget_ms=3000,
        )

    assert transition.await_args_list == [
        call(
            conversation=conversation,
            target_state="RECORDING",
            actor_id=actor.actor_id,
            trace_id="correlation-1",
            idempotency_key="turn-1",
        ),
        call(
            conversation=conversation,
            target_state="PROCESSING",
            actor_id=actor.actor_id,
            trace_id="correlation-1",
            idempotency_key="turn-1",
        ),
    ]
    session.add.assert_not_called()
