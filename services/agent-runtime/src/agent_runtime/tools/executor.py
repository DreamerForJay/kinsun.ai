from typing import Protocol

from agent_runtime.contracts.models import ToolRequest, ToolResult


class ToolExecutor(Protocol):
    """Boundary used by orchestration without depending on an HTTP implementation."""

    async def execute(self, request: ToolRequest) -> ToolResult: ...
