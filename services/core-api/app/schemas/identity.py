"""Pydantic schemas for Identity API endpoints.

Defines request/response models for:
- GET /api/v1/me → MeResponse
- GET /api/v1/me/authorized-elders → AuthorizedEldersResponse

All responses are wrapped in SuccessEnvelope at the handler layer.
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ElderMode(str, Enum):
    """Valid mode values for the authorized-elders query parameter."""

    DAYCARE = "daycare"
    HOME_CARE = "home-care"
    FAMILY = "family"


class MeResponse(BaseModel):
    """Response schema for GET /api/v1/me.

    Contains the authenticated actor's profile information.
    """

    model_config = ConfigDict(from_attributes=True)

    actor_id: UUID
    actor_type: str
    display_name: str
    tenant_id: UUID
    role: str
    care_unit_ids: list[UUID]
    elder_id: UUID | None = None


class AuthorizedElderItem(BaseModel):
    """A single elder entry in the authorized-elders listing."""

    model_config = ConfigDict(from_attributes=True)

    elder_id: UUID
    display_name: str
    care_unit_name: str | None = None
    authorization_summary: str | None = None


class PaginationMeta(BaseModel):
    """Cursor-based pagination metadata."""

    next_cursor: str | None = None
    has_more: bool
    limit: int = Field(ge=1, le=100)


class AuthorizedEldersResponse(BaseModel):
    """Response schema for GET /api/v1/me/authorized-elders.

    Contains paginated list of elders the actor is authorized to access.
    Wrapped in SuccessEnvelope.data at the handler layer.
    """

    items: list[AuthorizedElderItem]
    page: PaginationMeta
