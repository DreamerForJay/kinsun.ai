from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

import httpx
from pydantic import Field, ValidationError

from agent_runtime.contracts.models import ContractBaseModel
from agent_runtime.core.envelopes import ErrorEnvelope, SuccessEnvelope

AGENT_RUN_REGISTRATION_PATH = "/api/v1/internal/agent-runs"

TerminalAgentRunStatus = Literal[
    "SUCCESS",
    "NEEDS_CLARIFICATION",
    "BLOCKED",
    "HUMAN_REVIEW",
    "NO_DATA",
    "SCHEMA_FAILED",
    "DEPENDENCY_FAILED",
    "TIME_BUDGET_EXCEEDED",
    "COST_BUDGET_EXCEEDED",
    "CANCELLED",
]


class RegisterAgentRunRequest(ContractBaseModel):
    """Trusted registration metadata sent to Core before Tool execution."""

    session_id: UUID | None
    elder_id: UUID
    agent_id: str = Field(min_length=1, max_length=120)
    agent_version: str = Field(min_length=1, max_length=64)
    policy_version: str = Field(min_length=1, max_length=80)
    trace_id: str = Field(min_length=1, max_length=80)


class AgentRunRegistration(ContractBaseModel):
    """Core-owned identity and immutable scope returned by registration."""

    agent_run_id: UUID
    session_id: UUID | None
    elder_id: UUID
    agent_id: str
    agent_version: str
    result_status: Literal["RUNNING"]
    policy_version: str
    trace_id: str


class CompleteAgentRunRequest(ContractBaseModel):
    """Terminal outcome sent to Core's compare-and-set command."""

    result_status: TerminalAgentRunStatus
    stop_reason: str | None = Field(default=None, min_length=1, max_length=160)


class AgentRunCompletion(ContractBaseModel):
    """Canonical terminal state returned by Core."""

    agent_run_id: UUID
    session_id: UUID | None
    elder_id: UUID
    agent_id: str
    agent_version: str
    result_status: TerminalAgentRunStatus
    policy_version: str
    trace_id: str
    stop_reason: str | None
    completed_at: datetime


class AgentRunRegistrar(Protocol):
    async def register(
        self,
        request: RegisterAgentRunRequest,
        *,
        idempotency_key: str,
    ) -> AgentRunRegistration: ...


class AgentRunCompleter(Protocol):
    async def complete(
        self,
        agent_run_id: UUID,
        request: CompleteAgentRunRequest,
        *,
        idempotency_key: str,
    ) -> AgentRunCompletion: ...


class CoreAgentRunClientError(Exception):
    """Sanitized base error for Core AgentRun lifecycle failures."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.retryable = retryable
        self.status_code = status_code


class CoreAgentRunTimeoutError(CoreAgentRunClientError):
    def __init__(self) -> None:
        super().__init__(
            "Core AgentRun request timed out",
            reason_code="CORE_AGENT_RUN_TIMEOUT",
            retryable=True,
        )


class CoreAgentRunTransportError(CoreAgentRunClientError):
    def __init__(self) -> None:
        super().__init__(
            "Core AgentRun service is unavailable",
            reason_code="CORE_AGENT_RUN_UNAVAILABLE",
            retryable=True,
        )


class CoreAgentRunProtocolError(CoreAgentRunClientError):
    def __init__(self, *, status_code: int | None = None) -> None:
        super().__init__(
            "Core AgentRun response did not match the lifecycle contract",
            reason_code="CORE_AGENT_RUN_PROTOCOL_ERROR",
            retryable=False,
            status_code=status_code,
        )


class CoreAgentRunHttpError(CoreAgentRunClientError):
    """A valid Core ErrorEnvelope returned for a non-success status."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        reason_code: str | None,
        retryable: bool,
    ) -> None:
        super().__init__(
            "Core AgentRun lifecycle request was rejected",
            reason_code=reason_code or code,
            retryable=retryable,
            status_code=status_code,
        )
        self.code = code


class CoreAgentRunHttpClient:
    """Single-attempt adapter for Core-owned registration and completion.

    Authentication is deliberately outside this adapter. The injected client
    must already carry the approved request-scoped service credential.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def register(
        self,
        request: RegisterAgentRunRequest,
        *,
        idempotency_key: str,
    ) -> AgentRunRegistration:
        self._validate_idempotency_key(idempotency_key)
        response = await self._post(
            AGENT_RUN_REGISTRATION_PATH,
            request.model_dump(mode="json"),
            idempotency_key,
        )
        if response.status_code != 201:
            self._raise_http_error(response)
        registration = self._parse_success(response, AgentRunRegistration)
        if not self._registration_matches(registration, request):
            raise CoreAgentRunProtocolError(status_code=response.status_code)
        return registration

    async def complete(
        self,
        agent_run_id: UUID,
        request: CompleteAgentRunRequest,
        *,
        idempotency_key: str,
    ) -> AgentRunCompletion:
        self._validate_idempotency_key(idempotency_key)
        response = await self._post(
            f"{AGENT_RUN_REGISTRATION_PATH}/{agent_run_id}/complete",
            request.model_dump(mode="json"),
            idempotency_key,
        )
        if response.status_code != 200:
            self._raise_http_error(response)
        completion = self._parse_success(response, AgentRunCompletion)
        if (
            completion.agent_run_id != agent_run_id
            or completion.result_status != request.result_status
            or completion.stop_reason != request.stop_reason
        ):
            raise CoreAgentRunProtocolError(status_code=response.status_code)
        return completion

    async def _post(
        self,
        path: str,
        payload: dict[str, object],
        idempotency_key: str,
    ) -> httpx.Response:
        try:
            return await self._client.post(
                path,
                headers={"Idempotency-Key": idempotency_key},
                json=payload,
            )
        except httpx.TimeoutException:
            raise CoreAgentRunTimeoutError from None
        except httpx.RequestError:
            raise CoreAgentRunTransportError from None

    @staticmethod
    def _validate_idempotency_key(idempotency_key: str) -> None:
        if not idempotency_key.strip() or len(idempotency_key) > 160:
            raise CoreAgentRunProtocolError()

    @staticmethod
    def _parse_success(response: httpx.Response, model_type):
        try:
            envelope = SuccessEnvelope[model_type].model_validate_json(response.content)
        except ValidationError:
            raise CoreAgentRunProtocolError(status_code=response.status_code) from None
        return envelope.data

    @staticmethod
    def _registration_matches(
        registration: AgentRunRegistration,
        request: RegisterAgentRunRequest,
    ) -> bool:
        return (
            registration.session_id == request.session_id
            and registration.elder_id == request.elder_id
            and registration.agent_id == request.agent_id
            and registration.agent_version == request.agent_version
            and registration.policy_version == request.policy_version
            and registration.trace_id == request.trace_id
        )

    @staticmethod
    def _raise_http_error(response: httpx.Response) -> None:
        try:
            envelope = ErrorEnvelope.model_validate_json(response.content)
        except ValidationError:
            raise CoreAgentRunProtocolError(status_code=response.status_code) from None
        raise CoreAgentRunHttpError(
            status_code=response.status_code,
            code=envelope.error.code,
            reason_code=envelope.error.reason_code,
            retryable=envelope.error.retryable,
        )
