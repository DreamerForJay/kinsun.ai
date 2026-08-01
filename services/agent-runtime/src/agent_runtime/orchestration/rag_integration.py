from __future__ import annotations

from typing import Protocol

from agent_runtime.common.enums import ActorRole, RiskLevel, SafetyDecision
from agent_runtime.contracts.models import AgentRunRequest, SafetyEvaluation
from agent_runtime.rag.fallback import failed_response
from agent_runtime.rag.models import (
    QueryProfile,
    RetrievalRequestV1,
    RetrievalResponseV1,
)

RAG_PURPOSES: dict[str, QueryProfile] = {
    "general_information": "natural_language",
    "legal_reference": "legal",
}

AUDIENCE_BY_ROLE = {
    ActorRole.ELDER: "elder",
    ActorRole.FAMILY: "family_caregiver",
    ActorRole.STAFF: "care_professional",
    ActorRole.SYSTEM: "system_admin",
}


class RagRetriever(Protocol):
    async def retrieve(self, request: RetrievalRequestV1) -> RetrievalResponseV1: ...


def is_rag_request(request: AgentRunRequest) -> bool:
    """Conservatively route only requests carrying an explicit knowledge purpose."""

    return _normalized_purpose(request.purpose) in RAG_PURPOSES


def build_retrieval_request(request: AgentRunRequest) -> RetrievalRequestV1:
    purpose = _normalized_purpose(request.purpose)
    profile = RAG_PURPOSES[purpose]
    return RetrievalRequestV1(
        schema_version="1.0.0",
        request_id=request.request_id,
        query=request.input_text,
        query_profile=profile,
        top_k=5,
        audience=AUDIENCE_BY_ROLE[request.actor_role],
        purpose=purpose,
        language=request.language,
    )


async def retrieve_for_agent(
    request: AgentRunRequest,
    retriever: RagRetriever | None,
) -> RetrievalResponseV1:
    """Return a sanitized FAILED outcome for missing or faulty retrieval adapters."""

    if retriever is None:
        return failed_response(request.request_id)
    try:
        retrieval_request = build_retrieval_request(request)
        response = await retriever.retrieve(retrieval_request)
        if response.request_id != request.request_id:
            return failed_response(request.request_id)
        return response
    except Exception:
        # Do not expose provider errors or the elder's query in the Agent reply.
        return failed_response(request.request_id)


def retrieval_fallback_safety(response: RetrievalResponseV1) -> SafetyEvaluation:
    """Represent a no-guess retrieval outcome using the existing Agent wire contract."""

    if response.status == "SUCCESS" or response.fallback_message is None:
        raise ValueError("retrieval fallback safety requires a non-success response")
    return SafetyEvaluation(
        decision=SafetyDecision.SAFE_FALLBACK,
        risk_level=RiskLevel.LOW,
        reason_codes=[f"RAG_{response.status}"],
        matched_terms=[],
        safe_reply=response.fallback_message,
    )


def _normalized_purpose(value: str) -> str:
    return value.strip().casefold().replace("-", "_")
