"""Strict private ASR submission and safe public gate-decision schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.conversation import LanguageRoute


class SubmitAsrResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    language_route: LanguageRoute
    asr_model_version: str = Field(min_length=1, max_length=160)
    confidence: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)
    transcript: str = Field(min_length=1, max_length=4000)

    @field_validator("transcript")
    @classmethod
    def reject_blank_transcript(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("transcript must contain non-whitespace content")
        return value


class ConfirmAsrGateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["CONFIRM", "REJECT"]


class AsrGateDecisionResponse(BaseModel):
    """Deliberately excludes transcript, confidence, digest and ticket."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    decision: Literal["CAN_SEND_TO_AGENT", "CONFIRMATION_REQUIRED", "CANNOT_SEND_TO_AGENT"]
    confirmation_required: bool
    expires_at: datetime
