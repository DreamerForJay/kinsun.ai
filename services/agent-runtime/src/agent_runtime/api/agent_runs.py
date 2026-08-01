from __future__ import annotations

import httpx
from fastapi import APIRouter, Request

from agent_runtime.common.errors import InvalidRequestError
from agent_runtime.contracts.models import AgentRunRequest, AgentRunResponse
from agent_runtime.core.agent_runs import CoreAgentRunHttpClient
from agent_runtime.core.envelopes import ResponseMeta, SuccessEnvelope
from agent_runtime.middleware.correlation import get_correlation_id
from agent_runtime.settings import get_settings
from agent_runtime.tools.core_client import CoreToolHttpClient
from agent_runtime.tools.requests import CREATE_EVENT_CANDIDATE_TOOL
from agent_runtime.tracing.trace import new_trace_id

router = APIRouter()


@router.post("/api/v1/agent/runs", response_model=SuccessEnvelope[AgentRunResponse])
async def run_agent(
    request: Request, payload: AgentRunRequest
) -> SuccessEnvelope[AgentRunResponse]:
    """Run one bounded agent turn and any explicitly allowlisted Tool write."""
    orchestrator = request.app.state.orchestrator

    if payload.trace_id is None:
        payload.trace_id = new_trace_id()

    if CREATE_EVENT_CANDIDATE_TOOL not in payload.allowed_tools:
        response = await orchestrator.run(payload)
        return _envelope(response)

    settings = get_settings()
    if settings.CORE_API_BASE_URL is None:
        response = await orchestrator.run(payload)
        return _envelope(response)

    authorization_values = request.headers.getlist("authorization")
    if len(authorization_values) > 1:
        raise InvalidRequestError("Authorization header must not be repeated")

    headers = {"Authorization": authorization_values[0]} if authorization_values else None
    async with httpx.AsyncClient(
        base_url=str(settings.CORE_API_BASE_URL),
        headers=headers,
        timeout=settings.CORE_API_TIMEOUT_SECONDS,
    ) as core_http_client:
        response = await orchestrator.run(
            payload,
            agent_run_registrar=CoreAgentRunHttpClient(core_http_client),
            tool_executor=CoreToolHttpClient(core_http_client),
        )
    return _envelope(response)


def _envelope(response: AgentRunResponse) -> SuccessEnvelope[AgentRunResponse]:
    return SuccessEnvelope(
        data=response,
        meta=ResponseMeta(correlation_id=get_correlation_id()),
    )
