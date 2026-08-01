from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

import httpx
from pydantic import Field, ValidationError

from agent_runtime.contracts.models import ContractBaseModel
from agent_runtime.core.envelopes import ErrorEnvelope, SuccessEnvelope

AGENT_RUN_REGISTRATION_PATH = "/api/v1/internal/agent-runs"


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


class AgentRunRegistrar(Protocol):
    """Boundary used by orchestration without depending on HTTP."""

    async def register(
        self,
        request: RegisterAgentRunRequest,
        *,
        idempotency_key: str,
    ) -> AgentRunRegistration: ...


class CoreAgentRunClientError(Exception):
    """Sanitized base error for Core registration failures."""

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
            "Core AgentRun response did not match the registration contract",
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
            "Core AgentRun registration was rejected",
            reason_code=reason_code or code,
            retryable=retryable,
            status_code=status_code,
        )
        self.code = code


class CoreAgentRunHttpClient:
    """Single-attempt adapter for Core-owned AgentRun registration.

    Authentication is deliberately outside this adapter. The injected
    ``httpx.AsyncClient`` must already carry the approved caller credential;
    this class never creates or substitutes an Authorization header.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def register(
        self,
        request: RegisterAgentRunRequest,
        *,
        idempotency_key: str,
    ) -> AgentRunRegistration:
        if not idempotency_key.strip() or len(idempotency_key) > 160:
            raise CoreAgentRunProtocolError()

        try:
            response = await self._client.post(
                AGENT_RUN_REGISTRATION_PATH,
                headers={"Idempotency-Key": idempotency_key},
                json=request.model_dump(mode="json"),
            )
        except httpx.RequestError:
            raise CoreAgentRunTransportError from None

        if response.status_code != 201:
            self._raise_http_error(response)

        registration = self._parse_success(response)
        if not self._matches_request(registration, request):
            raise CoreAgentRunProtocolError(status_code=response.status_code)
        return registration

    @staticmethod
    def _parse_success(response: httpx.Response) -> AgentRunRegistration:
        try:
            envelope = SuccessEnvelope[AgentRunRegistration].model_validate_json(response.content)
        except ValidationError:
            raise CoreAgentRunProtocolError(status_code=response.status_code) from None
        return envelope.data

    @staticmethod
    def _matches_request(
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
