"""Server-to-server Agent Runtime adapter tests."""

from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.agent_runtime import AgentRuntimeClient
from app.core.exceptions import ServiceUnavailableError


def _success_payload() -> dict:
    return {
        "data": {
            "schema_version": "1.0.0",
            "request_id": "req-1",
            "trace_id": "trace-1",
            "agent_run_id": "run-2a6f9c31-8e47-4b52-9d10-3c8a7e5b1a40",
            "selected_agent": "companion-agent",
            "reply_text": "這是安全的合成回覆。",
            "reply_language": "zh-TW",
            "safety_result": {
                "schema_version": "1.0.0",
                "decision": "ALLOW",
                "risk_level": "LOW",
                "reason_codes": ["ALLOW"],
                "matched_terms": [],
                "safe_reply": None,
            },
            "context_manifest_id": "context-1",
            "step_count": 1,
            "result_status": "SUCCESS",
            "reason_codes": ["ALLOW"],
        },
        "meta": {
            "correlation_id": "correlation-1",
            "timestamp": "2026-08-01T00:00:00Z",
            "schema_version": "1.0",
        },
    }


def _event_candidate_proposal() -> dict:
    return {
        "event_type": "MEAL",
        "event_time": None,
        "structured_payload": {
            "observation_basis": "ELDER_STATEMENT",
            "meal_status": "CONSUMED",
            "meal_period": "BREAKFAST",
        },
        "evidence_refs": [],
        "confidence_band": "MEDIUM",
        "review_requirement": "REQUIRED",
        "extractor_version": "event-extractor-v1",
    }


@pytest.mark.asyncio
async def test_agent_runtime_client_posts_contract_and_validates_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["correlation_id"] = request.headers["X-Correlation-ID"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_success_payload())

    client = AgentRuntimeClient(
        base_url="http://agent-runtime:8001/",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    payload = {"request_id": "req-1", "input_text": "合成測試文字"}

    result = await client.run(request_payload=payload, correlation_id="correlation-1")

    assert captured == {
        "path": "/api/v1/agent/runs",
        "correlation_id": "correlation-1",
        "payload": payload,
    }
    assert result.reply_text == "這是安全的合成回覆。"


@pytest.mark.asyncio
async def test_agent_runtime_client_accepts_minimized_event_candidate_proposal() -> None:
    payload = _success_payload()
    payload["data"]["event_candidate_proposal"] = _event_candidate_proposal()
    client = AgentRuntimeClient(
        base_url="http://agent-runtime:8001",
        timeout_seconds=1,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
    )

    result = await client.run(request_payload={}, correlation_id="correlation-1")

    assert result.event_candidate_proposal is not None
    assert result.event_candidate_proposal.event_type == "MEAL"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda proposal: proposal.update({"elder_id": "not-runtime-authority"}),
        lambda proposal: proposal["structured_payload"].update(
            {"transcript": "restricted synthetic transcript"}
        ),
        lambda proposal: proposal["structured_payload"].update(
            {"elder_id": "runtime-must-not-supply-scope"}
        ),
    ],
)
async def test_agent_runtime_client_rejects_proposal_scope_or_restricted_data(mutate) -> None:
    payload = _success_payload()
    proposal = _event_candidate_proposal()
    mutate(proposal)
    payload["data"]["event_candidate_proposal"] = proposal
    client = AgentRuntimeClient(
        base_url="http://agent-runtime:8001",
        timeout_seconds=1,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
    )

    with pytest.raises(ServiceUnavailableError, match="Agent runtime is unavailable"):
        await client.run(request_payload={}, correlation_id="correlation-1")


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [500, 503])
async def test_agent_runtime_client_maps_dependency_failure(status_code: int) -> None:
    client = AgentRuntimeClient(
        base_url="http://agent-runtime:8001",
        timeout_seconds=1,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(status_code, json={"error": {}})
        ),
    )

    with pytest.raises(ServiceUnavailableError, match="Agent runtime is unavailable"):
        await client.run(request_payload={}, correlation_id="correlation-1")


@pytest.mark.asyncio
async def test_agent_runtime_client_rejects_uncontracted_response_fields() -> None:
    payload = _success_payload()
    payload["data"]["input_text"] = "must not be echoed"
    client = AgentRuntimeClient(
        base_url="http://agent-runtime:8001",
        timeout_seconds=1,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
    )

    with pytest.raises(ServiceUnavailableError, match="Agent runtime is unavailable"):
        await client.run(request_payload={}, correlation_id="correlation-1")


@pytest.mark.asyncio
async def test_agent_runtime_client_rejects_correlation_mismatch() -> None:
    payload = _success_payload()
    payload["meta"]["correlation_id"] = "different-correlation"
    client = AgentRuntimeClient(
        base_url="http://agent-runtime:8001",
        timeout_seconds=1,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
    )

    with pytest.raises(ServiceUnavailableError, match="correlation mismatch"):
        await client.run(request_payload={}, correlation_id="correlation-1")
