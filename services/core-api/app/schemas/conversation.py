"""Conversation-session API schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LanguageRoute(str, Enum):
    ZH_TW = "ZH_TW"
    NAN_TW = "NAN_TW"
    HAK_TW = "HAK_TW"
    EN_US = "EN_US"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class CreateVoiceSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language_preference: LanguageRoute
    input_mode: Literal["voice", "text", "voice_with_text_fallback"]
    client_audio_format: str | None = Field(default=None, max_length=80)
    client_timezone: str = Field(default="Asia/Taipei", min_length=1, max_length=64)
    purpose: Literal["BASIC_VOICE"] = "BASIC_VOICE"


class CreateVoiceTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language_preference: LanguageRoute
    input_mode: Literal["voice", "voice_with_text_fallback"]
    client_audio_format: str | None = Field(default=None, max_length=80)
    client_timezone: str = Field(default="Asia/Taipei", min_length=1, max_length=64)
    purpose: Literal["BASIC_VOICE"] = "BASIC_VOICE"


class ConsumeVoiceTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    voice_ticket: str = Field(min_length=32, max_length=128)


class TransitionVoiceSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: Literal[
        "RECORDING",
        "PROCESSING",
        "RESPONDING",
        "COMPLETED",
        "CANCELLED",
        "FAILED",
    ]


class CompanionTurnRequest(BaseModel):
    """Ephemeral current-turn text; Core never returns or stores this value."""

    model_config = ConfigDict(extra="forbid")

    input_text: str = Field(min_length=1, max_length=4000)

    @field_validator("input_text")
    @classmethod
    def reject_blank_input(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("input_text must contain non-whitespace content")
        return value


class CompanionTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    agent_run_id: UUID
    trace_id: str = Field(min_length=1, max_length=128)
    context_manifest_id: str = Field(min_length=1, max_length=128)
    reply_text: str = Field(min_length=1, max_length=4000)
    reply_language: str = Field(min_length=2, max_length=10)
    result_status: Literal["SUCCESS", "BLOCKED", "SAFE_FALLBACK", "FAILED"]
    safety_decision: Literal["ALLOW", "BLOCK", "SAFE_FALLBACK", "HUMAN_REVIEW"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    reason_codes: list[str]
    session_state: Literal["COMPLETED"] = "COMPLETED"
    transport_status: Literal["TEXT_ONLY"] = "TEXT_ONLY"
    model_route: str = Field(min_length=1, max_length=200)


class VoiceSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    elder_id: UUID
    state: Literal[
        "CREATED",
        "RECORDING",
        "PROCESSING",
        "RESPONDING",
        "COMPLETED",
        "CANCELLED",
        "FAILED",
    ]
    language_route: LanguageRoute
    consent_version: int
    policy_version: str | None
    started_at: datetime
    ended_at: datetime | None
    transport_status: Literal["NOT_CONFIGURED", "AVAILABLE"] = "NOT_CONFIGURED"
    websocket_url: str | None = None
    connection_token: str | None = None


class VoiceTicketIssuedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_session: VoiceSessionResponse
    voice_ticket: str = Field(min_length=32, max_length=128)
    expires_at: datetime
    transport_status: Literal["TICKET_ISSUED"] = "TICKET_ISSUED"
