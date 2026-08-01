from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from agent_runtime.agents.event_extractor.models import (
    CareEventType,
    ConfidenceBand,
    CreateCareEventCandidateRequestV1,
    EventSourceType,
)
from agent_runtime.contracts.models import ToolRequest, ToolResult
from agent_runtime.tools.requests import build_create_event_candidate_request

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_ROOT = REPOSITORY_ROOT / "contracts" / "schemas"
TOOL_CALL_ID = UUID("11111111-1111-4111-8111-111111111111")
AGENT_RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
ELDER_ID = UUID("33333333-3333-4333-8333-333333333333")
SOURCE_ID = UUID("44444444-4444-4444-8444-444444444444")
RESOURCE_ID = UUID("55555555-5555-4555-8555-555555555555")


def _validate_contract(schema_name: str, payload: dict[str, object]) -> None:
    schema = json.loads((CONTRACTS_ROOT / "tools" / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def _candidate() -> CreateCareEventCandidateRequestV1:
    return CreateCareEventCandidateRequestV1(
        source_type=EventSourceType.CONVERSATION_SESSION,
        source_id=SOURCE_ID,
        event_type=CareEventType.MEAL,
        structured_payload={
            "observation_basis": "ELDER_STATEMENT",
            "meal_status": "CONSUMED",
            "meal_period": "BREAKFAST",
        },
        evidence_refs=[f"evidence:{SOURCE_ID}"],
        confidence_band=ConfidenceBand.MEDIUM,
        extractor_version="event-extractor-v1",
    )


def _tool_request(**updates: object) -> ToolRequest:
    payload: dict[str, object] = {
        "tool_call_id": TOOL_CALL_ID,
        "agent_run_id": AGENT_RUN_ID,
        "tool_name": "create_event_candidate",
        "tool_version": "1.0",
        "elder_id": ELDER_ID,
        "purpose": "CARE_EVENT_EXTRACTION",
        "consent_version": 1,
        "policy_version": "policy-v1",
        "request_id": "request-1",
        "idempotency_key": "event-candidate-1",
        "parameters": _candidate().model_dump(mode="json"),
    }
    payload.update(updates)
    return ToolRequest.model_validate(payload)


def test_tool_request_and_result_match_executable_json_schemas() -> None:
    request = _tool_request()
    result = ToolResult(
        result_status="SUCCESS",
        resource_id=RESOURCE_ID,
        resource_version=1,
        source_refs=[SOURCE_ID],
        retryable=False,
        trace_id="trace-1",
    )

    _validate_contract("ToolRequestV1.json", request.model_dump(mode="json"))
    _validate_contract("ToolResultV1.json", result.model_dump(mode="json"))


def test_create_event_candidate_factory_preserves_typed_trusted_context() -> None:
    request = build_create_event_candidate_request(
        candidate=_candidate(),
        tool_call_id=TOOL_CALL_ID,
        agent_run_id=AGENT_RUN_ID,
        elder_id=ELDER_ID,
        consent_version=3,
        policy_version="policy-v3",
        request_id="request-3",
        idempotency_key="event-candidate-3",
    )

    assert request.tool_name == "create_event_candidate"
    assert request.tool_version == "1.0"
    assert request.purpose == "CARE_EVENT_EXTRACTION"
    assert request.agent_run_id == AGENT_RUN_ID
    assert request.elder_id == ELDER_ID
    assert request.consent_version == 3
    assert request.parameters["source_id"] == str(SOURCE_ID)
    assert "transcript" not in request.parameters
    _validate_contract("ToolRequestV1.json", request.model_dump(mode="json"))


def test_tool_request_rejects_restricted_keys_at_any_depth() -> None:
    with pytest.raises(ValidationError, match="restricted field"):
        _tool_request(parameters={"safe": {"nested": {"transcript": "restricted"}}})


@pytest.mark.parametrize("idempotency_key", ["", "   "])
def test_create_event_candidate_factory_requires_nonblank_idempotency_key(
    idempotency_key: str,
) -> None:
    with pytest.raises(ValueError, match="idempotency_key is required"):
        build_create_event_candidate_request(
            candidate=_candidate(),
            tool_call_id=TOOL_CALL_ID,
            agent_run_id=AGENT_RUN_ID,
            elder_id=ELDER_ID,
            consent_version=1,
            policy_version="policy-v1",
            request_id="request-1",
            idempotency_key=idempotency_key,
        )


def test_tool_result_parses_uuid_fields_from_wire_json() -> None:
    payload = {
        "result_status": "SUCCESS",
        "resource_id": str(RESOURCE_ID),
        "resource_version": 2,
        "source_refs": [str(SOURCE_ID)],
        "reason_code": None,
        "retryable": False,
        "redactions": [],
        "trace_id": "trace-2",
    }

    result = ToolResult.model_validate_json(json.dumps(payload))

    assert result.resource_id == RESOURCE_ID
    assert result.source_refs == [SOURCE_ID]
