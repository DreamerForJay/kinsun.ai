from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from agent_runtime.contracts.models import ToolRequest
from agent_runtime.tools.core_client import CoreToolHttpClient
from agent_runtime.tools.errors import (
    CoreToolHttpError,
    CoreToolProtocolError,
    CoreToolTransportError,
)

TOOL_CALL_ID = UUID("11111111-1111-4111-8111-111111111111")
AGENT_RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
ELDER_ID = UUID("33333333-3333-4333-8333-333333333333")
RESOURCE_ID = UUID("55555555-5555-4555-8555-555555555555")


def _tool_request() -> ToolRequest:
    return ToolRequest(
        tool_call_id=TOOL_CALL_ID,
        agent_run_id=AGENT_RUN_ID,
        tool_name="create_event_candidate",
        tool_version="1.0",
        elder_id=ELDER_ID,
        purpose="CARE_EVENT_EXTRACTION",
        consent_version=1,
        policy_version="policy-v1",
        request_id="request-1",
        idempotency_key="event-candidate-1",
        parameters={
            "source_type": "CONVERSATION_SESSION",
            "source_id": "44444444-4444-4444-8444-444444444444",
            "source_version": 1,
            "event_type": "MEAL",
            "event_time": None,
            "structured_payload": {
                "observation_basis": "ELDER_STATEMENT",
                "meal_status": "CONSUMED",
            },
            "evidence_refs": [],
            "confidence_band": "MEDIUM",
            "review_requirement": "REQUIRED",
            "extractor_version": "event-extractor-v1",
        },
    )


def _success_envelope(data: dict[str, object]) -> dict[str, object]:
    return {
        "data": data,
        "meta": {
            "correlation_id": "correlation-1",
            "timestamp": datetime(2026, 8, 1, tzinfo=UTC).isoformat(),
            "schema_version": "1.0",
        },
    }


def _error_envelope(
    *,
    code: str,
    reason_code: str,
    retryable: bool,
    message: str = "Rejected",
) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": "correlation-1",
            "reason_code": reason_code,
            "retryable": retryable,
            "details": None,
        }
    }


async def _execute_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
):
    async with httpx.AsyncClient(
        base_url="https://core.example.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        return await CoreToolHttpClient(http_client).execute(_tool_request())


@pytest.mark.asyncio
async def test_client_posts_once_without_inventing_auth_and_parses_success() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert request.method == "POST"
        assert request.url.path == "/api/v1/internal/tools/execute"
        assert "authorization" not in request.headers
        assert body["tool_name"] == "create_event_candidate"
        assert "transcript" not in json.dumps(body)
        return httpx.Response(
            200,
            json=_success_envelope(
                {
                    "result_status": "SUCCESS",
                    "data": None,
                    "resource_id": str(RESOURCE_ID),
                    "resource_version": 1,
                    "source_refs": [],
                    "reason_code": None,
                    "retryable": False,
                    "redactions": [],
                    "trace_id": "tool-trace-1",
                }
            ),
        )

    result = await _execute_with_handler(handler)

    assert len(calls) == 1
    assert result.result_status == "SUCCESS"
    assert result.resource_id == RESOURCE_ID


@pytest.mark.asyncio
async def test_blocked_tool_result_is_returned_without_transport_exception() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_envelope(
                {
                    "result_status": "BLOCKED",
                    "reason_code": "CONSENT_VERSION_MISMATCH",
                    "retryable": False,
                    "trace_id": "tool-trace-2",
                }
            ),
        )

    result = await _execute_with_handler(handler)

    assert result.result_status == "BLOCKED"
    assert result.reason_code == "CONSENT_VERSION_MISMATCH"
    assert result.retryable is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "reason_code", "retryable"),
    [
        (403, "RESOURCE_NOT_FOUND_OR_FORBIDDEN", False),
        (503, "DEPENDENCY_UNAVAILABLE", True),
    ],
)
async def test_valid_core_error_envelope_becomes_sanitized_typed_error(
    status_code: int,
    reason_code: str,
    retryable: bool,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status_code,
            json=_error_envelope(
                code="core_error",
                reason_code=reason_code,
                retryable=retryable,
                message="sensitive transcript must not escape",
            ),
        )

    with pytest.raises(CoreToolHttpError) as captured:
        await _execute_with_handler(handler)

    assert calls == 1
    assert captured.value.status_code == status_code
    assert captured.value.reason_code == reason_code
    assert captured.value.retryable is retryable
    assert "sensitive" not in str(captured.value)
    assert "transcript" not in str(captured.value)


@pytest.mark.asyncio
async def test_malformed_success_envelope_fails_closed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_envelope(
                {
                    "result_status": "SUCCESS",
                    "trace_id": "tool-trace-3",
                    "unexpected": "field",
                }
            ),
        )

    with pytest.raises(CoreToolProtocolError) as captured:
        await _execute_with_handler(handler)

    assert captured.value.status_code == 200
    assert captured.value.retryable is False


@pytest.mark.asyncio
async def test_transport_timeout_is_sanitized_and_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("sensitive provider detail", request=request)

    with pytest.raises(CoreToolTransportError) as captured:
        await _execute_with_handler(handler)

    assert calls == 1
    assert captured.value.retryable is True
    assert "sensitive" not in str(captured.value)
