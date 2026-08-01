"""Tenant ORM model.

Represents an organizational tenant (care facility, agency, etc.).
Tenant IS the system-level isolation entity itself, so it does NOT use
TenantScopedMixin.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, pg_enum

#: eldercare_ai.tenant_type_enum
TENANT_TYPE_ENUM = pg_enum(
    "tenant_type_enum",
    "CARE_ORGANIZATION",
    "COMMUNITY_ORGANIZATION",
    "HOME_CARE_PROVIDER",
    "DEMO",
    "HOUSEHOLD",
)


class Tenant(BaseModel):
    """Organizational tenant — the top-level isolation boundary.

    Inherits id (mapped onto tenant_id), created_at and updated_at from
    BaseModel. Does NOT use TenantScopedMixin because Tenant IS the isolation
    entity, and carries no version column in the baseline.
    """

    __tablename__ = "tenant"
    __pk_name__ = "tenant_id"

    tenant_type: Mapped[str] = mapped_column(
        TENANT_TYPE_ENUM,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        sa.String(160),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default=sa.text("'ACTIVE'"),
    )
    timezone: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        server_default=sa.text("'Asia/Taipei'"),
    )
    default_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
