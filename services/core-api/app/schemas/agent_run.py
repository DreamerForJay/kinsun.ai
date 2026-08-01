"""Internal AgentRun registration schemas."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RegisterAgentRunRequest(BaseModel):
    """Trusted runtime metadata used to create a Core-owned AgentRun row."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID | None
    elder_id: UUID
    agent_id: str = Field(min_length=1, max_length=120)
    agent_version: str = Field(min_length=1, max_length=64)
    policy_version: str = Field(min_length=1, max_length=80)
    trace_id: str = Field(min_length=1, max_length=80)


class AgentRunRegistrationResponse(BaseModel):
    """Safe registration result returned to the calling system service."""

    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    session_id: UUID | None
    elder_id: UUID
    agent_id: str
    agent_version: str
    result_status: Literal["RUNNING"]
    policy_version: str
    trace_id: str
