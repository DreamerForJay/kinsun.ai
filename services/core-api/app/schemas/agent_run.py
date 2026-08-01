"""Strict schemas for the internal AgentRun lifecycle."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
    """Original registration result returned to the calling system service."""

    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    session_id: UUID | None
    elder_id: UUID
    agent_id: str
    agent_version: str
    result_status: Literal["RUNNING"]
    policy_version: str
    trace_id: str


class CompleteAgentRunRequest(BaseModel):
    """Terminal outcome accepted by the compare-and-set completion command."""

    model_config = ConfigDict(extra="forbid")

    result_status: TerminalAgentRunStatus
    stop_reason: str | None = Field(default=None, min_length=1, max_length=160)


class AgentRunCompletionResponse(BaseModel):
    """Canonical terminal AgentRun state returned for completion and replay."""

    model_config = ConfigDict(extra="forbid")

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
