"""Schemas for Google-backed elder onboarding."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ElderOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str = Field(min_length=1, max_length=120)
    preferred_name: str | None = Field(default=None, min_length=1, max_length=80)
    preferred_language: Literal["ZH_TW", "NAN_TW", "HAK_TW", "EN_US"] = "ZH_TW"
    response_length_preference: Literal["SHORT", "STANDARD", "DETAILED"] = "SHORT"
    timezone: str = Field(default="Asia/Taipei", min_length=1, max_length=64)


class ElderOnboardingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: UUID
    tenant_id: UUID
    elder_id: UUID
    actor_type: Literal["ELDER"] = "ELDER"
    registration_status: Literal["ACTIVE"] = "ACTIVE"
    next_step: Literal["CONSENT"] = "CONSENT"
    replayed: bool = False


class ResolveOnboardingRequest(BaseModel):
    """BFF callback payload; role intent never grants authorization by itself."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    intent: Literal["ELDER", "FAMILY"]
    invitation_code: str | None = Field(default=None, min_length=16, max_length=24)


class ResolveOnboardingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["ELDER", "FAMILY"]
    actor_id: UUID
    tenant_id: UUID
    elder_id: UUID
    status: Literal["ACTIVE", "REDEEMED"]
    replayed: bool = False
