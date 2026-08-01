import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from pydantic import ValidationError as PydanticValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from agent_runtime.common.enums import RiskLevel, SafetyDecision
from agent_runtime.contracts.models import (
    AgentRunRequest,
    AgentRunResponse,
    ContextManifest,
    HandoffEnvelope,
    SafetyEvaluation,
)
from agent_runtime.rag.models import RetrievalRequestV1, RetrievalResponseV1

REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas"
EXAMPLE_DIR = REPO_ROOT / "contracts" / "examples"

SCHEMA_FILES = sorted(SCHEMA_DIR.rglob("*.json"))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_example(path: Path) -> dict:
    """Examples are wrapped in the validator's `data` envelope; models see the payload."""
    return load_json(path)["data"]


def build_registry() -> Registry:
    """Resolve the relative `$ref` between local schema files (handoff -> context manifest)."""
    resources = [
        (
            load_json(path)["$id"],
            Resource(contents=load_json(path), specification=DRAFT202012),
        )
        for path in SCHEMA_FILES
    ]
    return Registry().with_resources(resources)


def validator_for(schema_name: str) -> Draft202012Validator:
    schema = load_json(SCHEMA_DIR / schema_name)
    return Draft202012Validator(schema, registry=build_registry())


def make_context_manifest() -> ContextManifest:
    return ContextManifest(
        agent_id="companion-agent",
        elder_id="elder-001",
        tenant_id="tenant-001",
        purpose="conversation",
        consent_version="cv-2026.07.30",
        policy_version="pv-2026.07.30",
        items=[],
        excluded_items=[],
        total_token_estimate=0,
    )


def make_request_payload() -> dict:
    return load_example(EXAMPLE_DIR / "valid" / "agent-run-request.json")


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: p.name)
def test_every_schema_file_is_a_valid_draft_2020_12_schema(path):
    Draft202012Validator.check_schema(load_json(path))


@pytest.mark.parametrize(
    ("example_name", "schema_name"),
    [
        ("agent-run-request.json", "agent/AgentRunRequestV1.json"),
        ("agent-run-response.json", "agent/AgentRunResponseV1.json"),
    ],
)
def test_valid_examples_pass_json_schema(example_name, schema_name):
    validator_for(schema_name).validate(load_example(EXAMPLE_DIR / "valid" / example_name))


@pytest.mark.parametrize(
    ("example_name", "model"),
    [
        ("agent-run-request.json", AgentRunRequest),
        ("agent-run-response.json", AgentRunResponse),
    ],
)
def test_valid_examples_pass_pydantic_models(example_name, model):
    """The wire form accepted by JSON Schema must also be accepted by the Pydantic model."""
    model.model_validate(load_example(EXAMPLE_DIR / "valid" / example_name))


@pytest.mark.parametrize(
    ("example_name", "model"),
    [
        ("retrieval-request.json", RetrievalRequestV1),
        ("retrieval-response.json", RetrievalResponseV1),
    ],
)
def test_valid_rag_examples_pass_pydantic_models(example_name, model):
    model.model_validate(load_example(EXAMPLE_DIR / "valid" / example_name))


@pytest.mark.parametrize(
    ("example_name", "model"),
    [
        ("retrieval-request-top-k-ten.json", RetrievalRequestV1),
        ("retrieval-response-missing-source-url.json", RetrievalResponseV1),
    ],
)
def test_invalid_rag_examples_are_rejected_by_pydantic(example_name, model):
    with pytest.raises(PydanticValidationError):
        model.model_validate(load_example(EXAMPLE_DIR / "invalid" / example_name))


@pytest.mark.parametrize(
    "example_name",
    ["agent-run-request-extra-field.json", "agent-run-request-missing-required.json"],
)
def test_invalid_examples_rejected_by_json_schema(example_name):
    validator = validator_for("agent/AgentRunRequestV1.json")
    with pytest.raises(ValidationError):
        validator.validate(load_example(EXAMPLE_DIR / "invalid" / example_name))


@pytest.mark.parametrize(
    "example_name",
    ["agent-run-request-extra-field.json", "agent-run-request-missing-required.json"],
)
def test_invalid_examples_rejected_by_pydantic(example_name):
    """`additionalProperties: false` must be mirrored by `extra="forbid"` on the model."""
    with pytest.raises(PydanticValidationError):
        AgentRunRequest.model_validate(load_example(EXAMPLE_DIR / "invalid" / example_name))


def test_context_manifest_model_output_matches_schema():
    manifest = make_context_manifest()
    validator_for("agent/ContextManifestV1.json").validate(json.loads(manifest.model_dump_json()))


def test_safety_evaluation_model_output_matches_schema():
    evaluation = SafetyEvaluation(
        decision=SafetyDecision.ALLOW,
        risk_level=RiskLevel.LOW,
        reason_codes=["ALLOW"],
        matched_terms=[],
        safe_reply=None,
    )
    validator_for("agent/SafetyEvaluationV1.json").validate(
        json.loads(evaluation.model_dump_json())
    )


def test_handoff_envelope_model_output_matches_schema():
    envelope = HandoffEnvelope(
        request_id="req-001",
        trace_id="trace-001",
        workflow_instance_id="wf-001",
        session_id="sess-001",
        actor_id="actor-elder-001",
        actor_role="elder",
        elder_id="elder-001",
        tenant_id="tenant-001",
        purpose="conversation",
        consent_version="cv-2026.07.30",
        policy_version="pv-2026.07.30",
        language="zh-TW",
        risk_level="LOW",
        context_manifest=make_context_manifest(),
        context_budget=2048,
        allowed_tools=[],
        max_steps=3,
        latency_budget_ms=3000,
        parent_agent="conversation-orchestrator",
        handoff_reason="companion-to-safety",
    )
    validator_for("agent/HandoffEnvelopeV1.json").validate(json.loads(envelope.model_dump_json()))


@pytest.mark.parametrize(
    ("model", "schema_name"),
    [
        (AgentRunRequest, "agent/AgentRunRequestV1.json"),
        (AgentRunResponse, "agent/AgentRunResponseV1.json"),
        (ContextManifest, "agent/ContextManifestV1.json"),
        (SafetyEvaluation, "agent/SafetyEvaluationV1.json"),
        (HandoffEnvelope, "agent/HandoffEnvelopeV1.json"),
        (RetrievalRequestV1, "rag/retrieval-request.schema.json"),
        (RetrievalResponseV1, "rag/retrieval-response.schema.json"),
    ],
)
def test_model_fields_match_schema_properties(model, schema_name):
    schema = load_json(SCHEMA_DIR / schema_name)
    assert set(model.model_fields) == set(schema["properties"])


def test_schema_version_const_is_enforced_by_model():
    with pytest.raises(PydanticValidationError):
        AgentRunRequest.model_validate({**make_request_payload(), "schema_version": "9.9.9"})


def test_actor_role_enum_is_enforced_by_model():
    with pytest.raises(PydanticValidationError):
        AgentRunRequest.model_validate({**make_request_payload(), "actor_role": "intruder"})


def test_allowed_tools_pattern_is_enforced_by_model():
    with pytest.raises(PydanticValidationError):
        AgentRunRequest.model_validate({**make_request_payload(), "allowed_tools": ["NOT A TOOL!"]})


def test_trace_id_is_optional_on_both_sides():
    """The API generates a trace_id when the caller omits one, so neither side may require it."""
    schema = load_json(SCHEMA_DIR / "agent" / "AgentRunRequestV1.json")
    assert "trace_id" not in schema["required"]

    payload = make_request_payload()
    payload.pop("trace_id")
    validator_for("agent/AgentRunRequestV1.json").validate(payload)
    assert AgentRunRequest.model_validate(payload).trace_id is None
