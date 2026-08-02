from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from agent_runtime.common.enums import ActorRole, ResultStatus, RiskLevel, SafetyDecision

SCHEMA_VERSION = "1.0.0"
ID_REGEX = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
LANGUAGE_REGEX = r"^[a-z]{2,3}(?:-[A-Za-z]{2})?$"
TOOL_NAME_REGEX = r"^[a-z][a-z0-9_]{1,40}$"
EVIDENCE_REF_REGEX = (
    r"^evidence:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
TOOL_RESTRICTED_PARAMETER_KEYS = frozenset(
    {
        "audio",
        "audio_uri",
        "full_prompt",
        "prompt",
        "secret",
        "token",
        "transcript",
        "transcript_text",
    }
)
EVENT_PROPOSAL_RESTRICTED_KEYS = TOOL_RESTRICTED_PARAMETER_KEYS | {
    "actor_id",
    "actor_role",
    "agent_run_id",
    "asr_confidence",
    "consent_id",
    "consent_version",
    "elder_id",
    "input_text",
    "policy_version",
    "request_id",
    "session_id",
    "source_id",
    "source_type",
    "source_version",
    "tenant_id",
    "trace_id",
}

SchemaVersion = Literal["1.0.0"]
ToolName = Annotated[str, Field(pattern=TOOL_NAME_REGEX)]
RequestedOutput = Literal["event_candidate"]
EvidenceReference = Annotated[
    str,
    Field(min_length=45, max_length=45, pattern=EVIDENCE_REF_REGEX),
]

# JSON Schema declares these as plain strings drawn from an enum, so the contract models
# must accept that wire form. Strict mode is kept for every other field.
ActorRoleField = Annotated[ActorRole, Field(strict=False)]
ResultStatusField = Annotated[ResultStatus, Field(strict=False)]
RiskLevelField = Annotated[RiskLevel, Field(strict=False)]
SafetyDecisionField = Annotated[SafetyDecision, Field(strict=False)]


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


class ContractBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        strict=True,
        frozen=False,
    )


def _new_id() -> str:
    return f"id-{uuid4()}"


def _contains_restricted_tool_key(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(
            key.casefold() in TOOL_RESTRICTED_PARAMETER_KEYS or _contains_restricted_tool_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_restricted_tool_key(item) for item in value)
    return False


def _contains_restricted_event_key(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(
            key.casefold() in EVENT_PROPOSAL_RESTRICTED_KEYS or _contains_restricted_event_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_restricted_event_key(item) for item in value)
    return False


class ToolRequest(ContractBaseModel):
    """Executable wire request for Core's internal Tool endpoint."""

    tool_call_id: UUID
    agent_run_id: UUID
    tool_name: str = Field(min_length=1, max_length=120)
    tool_version: str = Field(pattern=r"^1\.", max_length=40)
    elder_id: UUID
    purpose: str = Field(min_length=1, max_length=64)
    consent_version: int = Field(ge=1)
    policy_version: str = Field(min_length=1, max_length=80)
    request_id: str = Field(min_length=1, max_length=80)
    idempotency_key: str | None = Field(default=None, max_length=160)
    expected_resource_version: int | None = Field(default=None, ge=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def reject_restricted_parameters(cls, parameters: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if _contains_restricted_tool_key(parameters):
            raise ValueError("parameters contain a restricted field")
        return parameters


class ToolResult(ContractBaseModel):
    """Executable wire result returned by Core, not legacy ToolResponseV1."""

    result_status: Literal["SUCCESS", "NO_DATA", "BLOCKED", "FAILED"]
    data: JsonValue | None = None
    resource_id: UUID | None = None
    resource_version: int | None = None
    source_refs: list[UUID] = Field(default_factory=list)
    reason_code: str | None = None
    retryable: bool = False
    redactions: list[str] = Field(default_factory=list)
    trace_id: str


class ContextItem(ContractBaseModel):
    item_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    source_type: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    content: str = Field(min_length=1, max_length=2048)
    token_estimate: int = Field(ge=0, le=10000)


class ExcludedContextItem(ContractBaseModel):
    source_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    reason_code: str = Field(min_length=1, max_length=128)


class ContextManifest(ContractBaseModel):
    schema_version: SchemaVersion = Field(default=SCHEMA_VERSION)
    context_manifest_id: str = Field(
        default_factory=_new_id,
        pattern=ID_REGEX,
        min_length=2,
        max_length=128,
    )
    agent_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    elder_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    tenant_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    purpose: str = Field(min_length=1, max_length=256)
    consent_version: str = Field(min_length=1, max_length=64)
    policy_version: str = Field(min_length=1, max_length=64)
    items: list[ContextItem] = Field(default_factory=list)
    excluded_items: list[ExcludedContextItem] = Field(default_factory=list)
    total_token_estimate: int = Field(ge=0, le=100000)
    created_at: datetime = Field(default_factory=_now_utc)
    expires_at: datetime = Field(default_factory=lambda: _now_utc() + timedelta(minutes=30))


class SafetyEvaluation(ContractBaseModel):
    schema_version: SchemaVersion = Field(default=SCHEMA_VERSION)
    decision: SafetyDecisionField
    risk_level: RiskLevelField
    reason_codes: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    safe_reply: str | None = None


class HandoffEnvelope(ContractBaseModel):
    schema_version: SchemaVersion = Field(default=SCHEMA_VERSION)
    request_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    trace_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    workflow_instance_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    session_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    actor_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    actor_role: ActorRoleField
    elder_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    tenant_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    purpose: str = Field(min_length=1, max_length=256)
    consent_version: str = Field(min_length=1, max_length=64)
    policy_version: str = Field(min_length=1, max_length=64)
    language: str = Field(pattern=LANGUAGE_REGEX, min_length=2, max_length=10)
    risk_level: RiskLevelField
    context_manifest: ContextManifest
    context_budget: int = Field(ge=1, le=100000)
    allowed_tools: list[ToolName] = Field(default_factory=list)
    max_steps: int = Field(ge=1, le=20)
    latency_budget_ms: int = Field(ge=100, le=300000)
    parent_agent: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    handoff_reason: str = Field(min_length=1, max_length=256)
    created_at: datetime = Field(default_factory=_now_utc)
    expires_at: datetime = Field(default_factory=lambda: _now_utc() + timedelta(minutes=30))


class AgentRunRequest(ContractBaseModel):
    schema_version: SchemaVersion = Field(default=SCHEMA_VERSION)
    request_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    trace_id: str | None = Field(default=None, pattern=ID_REGEX, min_length=2, max_length=128)
    agent_run_id: str | None = Field(
        default=None,
        pattern=ID_REGEX,
        min_length=2,
        max_length=128,
    )
    session_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    actor_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    actor_role: ActorRoleField
    elder_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    tenant_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    purpose: str = Field(min_length=1, max_length=256)
    consent_version: str = Field(min_length=1, max_length=64)
    policy_version: str = Field(min_length=1, max_length=64)
    language: str = Field(pattern=LANGUAGE_REGEX, min_length=2, max_length=10)
    input_text: str = Field(min_length=1, max_length=4000)
    allowed_tools: list[ToolName] = Field(default_factory=list)
    requested_outputs: list[RequestedOutput] = Field(default_factory=list, max_length=1)
    max_steps: int = Field(default=3, ge=1, le=20)
    latency_budget_ms: int = Field(ge=100, le=300000)


class EventCandidateProposal(ContractBaseModel):
    """Untrusted proposal only; Core supplies every scope and source fact."""

    event_type: Literal[
        "MEAL",
        "ACTIVITY",
        "SLEEP",
        "MEDICATION_STATEMENT",
        "EMOTION_EXPRESSION",
        "SOCIAL_CONTACT",
        "EXPECTED_CONTACT_MISSED",
        "ACTIVITY_PARTICIPATION",
        "ACTIVITY_CANCELLED",
        "COMPANIONSHIP_NEED",
    ]
    event_time: datetime | None = None
    structured_payload: dict[str, JsonValue]
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=16)
    confidence_band: Literal["LOW", "MEDIUM", "HIGH"]
    review_requirement: Literal["REQUIRED"] = "REQUIRED"
    extractor_version: str = Field(min_length=1, max_length=80)

    @field_validator("structured_payload")
    @classmethod
    def reject_restricted_payload_keys(
        cls,
        payload: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        if _contains_restricted_event_key(payload):
            raise ValueError("structured_payload contains a restricted field")
        return payload


class AgentRunResponse(ContractBaseModel):
    schema_version: SchemaVersion = Field(default=SCHEMA_VERSION)
    request_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    trace_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    agent_run_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    selected_agent: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    reply_text: str = Field(min_length=1, max_length=4000)
    reply_language: str = Field(pattern=LANGUAGE_REGEX, min_length=2, max_length=10)
    safety_result: SafetyEvaluation
    context_manifest_id: str = Field(pattern=ID_REGEX, min_length=2, max_length=128)
    step_count: int = Field(ge=1, le=20)
    result_status: ResultStatusField
    reason_codes: list[str] = Field(default_factory=list)
    event_candidate_proposal: EventCandidateProposal | None = None
