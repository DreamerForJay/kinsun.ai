"""Schemas for one-time family invitations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

FamilyShareScope = Literal[
    "REPORT_DAILY",
    "REPORT_WEEKLY",
    "REPORT_MONTHLY",
    "REPORT_IMPORTANT_EVENT",
]

DEFAULT_FAMILY_SHARE_SCOPES: list[FamilyShareScope] = [
    "REPORT_DAILY",
    "REPORT_WEEKLY",
    "REPORT_MONTHLY",
]


class CreateFamilyInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    invitee_email: str | None = Field(default=None, min_length=3, max_length=254)
    share_scope: list[FamilyShareScope] = Field(
        default_factory=lambda: list(DEFAULT_FAMILY_SHARE_SCOPES),
        min_length=1,
        max_length=4,
    )
    expires_in_hours: int = Field(default=24, ge=1, le=168)

    @field_validator("share_scope")
    @classmethod
    def reject_duplicate_scopes(cls, value: list[FamilyShareScope]) -> list[FamilyShareScope]:
        if len(value) != len(set(value)):
            raise ValueError("share_scope must not contain duplicates")
        return value


class FamilyInvitationCreatedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_id: UUID
    invitation_code: str
    status: Literal["ISSUED"] = "ISSUED"
    share_scope: list[FamilyShareScope]
    expires_at: datetime


class RedeemFamilyInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    invitation_code: str = Field(min_length=16, max_length=24)


class FamilyInvitationRedeemedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_id: UUID
    actor_id: UUID
    tenant_id: UUID
    elder_id: UUID
    relationship_id: UUID
    family_relationship_id: UUID
    status: Literal["REDEEMED"] = "REDEEMED"
    replayed: bool = False


class FamilyInvitationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_id: UUID
    status: Literal["ISSUED", "REDEEMED", "EXPIRED", "REVOKED", "LOCKED"]
    share_scope: list[FamilyShareScope]
    expires_at: datetime
    created_at: datetime


class FamilyInvitationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FamilyInvitationStatusResponse]
