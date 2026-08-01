"""Hash-only family invitation aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin, VersionedMixin


class FamilyInvitation(BaseModel, TenantScopedMixin, VersionedMixin):
    """One-time invitation from an elder to one family identity.

    Only keyed hashes are persisted.  The plaintext invitation code exists
    solely in the create response and must never be reconstructed or logged.
    """

    __tablename__ = "family_invitation"
    __pk_name__ = "family_invitation_id"

    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    issued_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    invitee_email_hmac: Mapped[str | None] = mapped_column(sa.CHAR(64))
    token_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False, unique=True)
    share_scope: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        server_default=sa.text("ARRAY['REPORT_DAILY','REPORT_WEEKLY','REPORT_MONTHLY']::varchar[]"),
    )
    consent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.consent_grant.consent_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=sa.text("'ISSUED'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=sa.text("0"),
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=sa.text("5"),
    )
    redeemed_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
