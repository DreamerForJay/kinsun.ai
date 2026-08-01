import httpx
from pydantic import ValidationError

from agent_runtime.contracts.models import ToolRequest, ToolResult
from agent_runtime.core.envelopes import ErrorEnvelope, SuccessEnvelope
from agent_runtime.tools.errors import (
    CoreToolHttpError,
    CoreToolProtocolError,
    CoreToolTimeoutError,
    CoreToolTransportError,
)

TOOL_EXECUTION_PATH = "/api/v1/internal/tools/execute"


class CoreToolHttpClient:
    """Single-attempt adapter for Core's executable Tool endpoint."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def execute(self, request: ToolRequest) -> ToolResult:
        try:
            response = await self._client.post(
                TOOL_EXECUTION_PATH,
                json=request.model_dump(mode="json"),
            )
        except httpx.TimeoutException:
            raise CoreToolTimeoutError from None
        except httpx.RequestError:
            raise CoreToolTransportError from None

        if response.status_code == 200:
            return self._parse_success(response)
        self._raise_http_error(response)

    @staticmethod
    def _parse_success(response: httpx.Response) -> ToolResult:
        try:
            envelope = SuccessEnvelope[ToolResult].model_validate_json(response.content)
        except ValidationError:
            raise CoreToolProtocolError(status_code=response.status_code) from None
        return envelope.data

    @staticmethod
    def _raise_http_error(response: httpx.Response) -> None:
        try:
            envelope = ErrorEnvelope.model_validate_json(response.content)
        except ValidationError:
            raise CoreToolProtocolError(status_code=response.status_code) from None

        raise CoreToolHttpError(
            status_code=response.status_code,
            code=envelope.error.code,
            reason_code=envelope.error.reason_code,
            retryable=envelope.error.retryable,
        )
