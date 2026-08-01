from uuid import UUID

from agent_runtime.agents.event_extractor.models import CreateCareEventCandidateRequestV1
from agent_runtime.contracts.models import ToolRequest

CREATE_EVENT_CANDIDATE_TOOL = "create_event_candidate"
CREATE_EVENT_CANDIDATE_TOOL_VERSION = "1.0"
CARE_EVENT_EXTRACTION_PURPOSE = "CARE_EVENT_EXTRACTION"


def build_create_event_candidate_request(
    *,
    candidate: CreateCareEventCandidateRequestV1,
    tool_call_id: UUID,
    agent_run_id: UUID,
    elder_id: UUID,
    consent_version: int,
    policy_version: str,
    request_id: str,
    idempotency_key: str,
) -> ToolRequest:
    """Build one executable write request without deriving trusted Core context."""

    if not idempotency_key.strip():
        raise ValueError("idempotency_key is required for create_event_candidate")

    return ToolRequest(
        tool_call_id=tool_call_id,
        agent_run_id=agent_run_id,
        tool_name=CREATE_EVENT_CANDIDATE_TOOL,
        tool_version=CREATE_EVENT_CANDIDATE_TOOL_VERSION,
        elder_id=elder_id,
        purpose=CARE_EVENT_EXTRACTION_PURPOSE,
        consent_version=consent_version,
        policy_version=policy_version,
        request_id=request_id,
        idempotency_key=idempotency_key,
        parameters=candidate.model_dump(mode="json"),
    )
