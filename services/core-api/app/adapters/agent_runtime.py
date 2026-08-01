"""Strict server-to-server adapter for the M0 Agent Runtime."""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError


class AgentSafetyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    decision: Literal["ALLOW", "BLOCK", "SAFE_FALLBACK", "HUMAN_REVIEW"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    reason_codes: list[str]
    matched_terms: list[str]
    safe_reply: str | None


class AgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    request_id: str
    trace_id: str
    agent_run_id: str
    selected_agent: str
    reply_text: str = Field(min_length=1, max_length=4000)
    reply_language: str
    safety_result: AgentSafetyResult
    context_manifest_id: str
    step_count: int
    result_status: Literal["SUCCESS", "BLOCKED", "SAFE_FALLBACK", "FAILED"]
    reason_codes: list[str]


class _AgentResponseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    timestamp: str
    schema_version: Literal["1.0"] = "1.0"


class _AgentRunEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: AgentRunResult
    meta: _AgentResponseMeta


class AgentRuntimeClient:
    """Call the private Agent Runtime and reject malformed responses."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def run(
        self,
        *,
        request_payload: dict[str, object],
        correlation_id: str,
    ) -> AgentRunResult:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/api/v1/agent/runs",
                    json=request_payload,
                    headers={"X-Correlation-ID": correlation_id},
                )
                response.raise_for_status()
            envelope = _AgentRunEnvelope.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise ServiceUnavailableError("Agent runtime is unavailable") from exc
        if envelope.meta.correlation_id != correlation_id:
            raise ServiceUnavailableError("Agent runtime response correlation mismatch")
        return envelope.data


def get_agent_runtime_client() -> AgentRuntimeClient:
    settings = get_settings()
    return AgentRuntimeClient(
        base_url=settings.agent_runtime_url,
        timeout_seconds=settings.agent_runtime_timeout_seconds,
    )
