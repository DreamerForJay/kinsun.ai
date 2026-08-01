"""A broken model provider must stay a visible dependency failure.

Two things must hold at once: the outage answers 5xx so it cannot hide inside
normal traffic, and the elder's words never reach the log. The unhandled
handler prints a full traceback, and a provider exception chain can quote the
request body, so this path must never reach it.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from agent_runtime.app import app
from agent_runtime.common.errors import ModelDependencyError
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.provider import ModelProvider

RUNS_PATH = "/api/v1/agent/runs"
ELDER_WORDS = "我昨天晚上睡不好，一直咳嗽。"


class BrokenProvider(ModelProvider):
    async def generate_reply(
        self, request: AgentRunRequest, context_manifest: ContextManifest, language: str
    ) -> str:
        try:
            # Stands in for botocore quoting the request it failed to send.
            raise RuntimeError(f"ValidationException while sending: {ELDER_WORDS}")
        except RuntimeError as exc:
            raise ModelDependencyError("Bedrock reply failed: RuntimeError") from exc


def make_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "request_id": "req-provider-down-001",
        "trace_id": "trace-provider-down-001",
        "session_id": "sess-provider-down-001",
        "actor_id": "actor-elder-001",
        "actor_role": "elder",
        "elder_id": "elder-001",
        "tenant_id": "tenant-001",
        "purpose": "conversation",
        "consent_version": "cv-2026.07.30",
        "policy_version": "pv-2026.07.30",
        "language": "zh-TW",
        "input_text": ELDER_WORDS,
        "allowed_tools": [],
        "max_steps": 2,
        "latency_budget_ms": 3000,
    }


@pytest.fixture
def broken_provider():
    companion = app.state.orchestrator.companion
    original = companion.provider
    companion.provider = BrokenProvider()
    try:
        yield
    finally:
        companion.provider = original


@pytest.mark.asyncio
async def test_provider_failure_is_a_503_and_not_a_conversational_success(
    broken_provider: None,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(RUNS_PATH, json=make_payload())

    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"error"}
    # A dependency outage is not a turn the elder completed.
    assert "data" not in body


@pytest.mark.asyncio
async def test_provider_failure_keeps_the_elder_transcript_out_of_the_log(
    broken_provider: None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="agent_runtime"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(RUNS_PATH, json=make_payload())

    assert response.status_code == 503
    logged = "\n".join(
        [record.getMessage() for record in caplog.records]
        + [str(getattr(record, "traceback", "")) for record in caplog.records]
    )
    assert ELDER_WORDS not in logged
    assert ELDER_WORDS not in response.text
    assert "unhandled_exception" not in logged
