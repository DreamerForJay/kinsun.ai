"""Server-side ASR gate evidence.

The transcript is restricted data.  It is optional by design: only an active
TRANSCRIPT_STORAGE consent permits persisting it.  The keyed digest remains
available for replay/audit correlation without making the text recoverable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin
from app.models.conversation import LANGUAGE_CODE_ENUM


class AsrGateEvidence(BaseModel, TenantScopedMixin):
    """One exactly-once ASR decision for one consumed voice session."""

    __tablename__ = "asr_gate_evidence"
    __pk_name__ = "asr_gate_evidence_id"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.conversation_session.session_id"),
        nullable=False,
        unique=True,
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    language_route: Mapped[str] = mapped_column(LANGUAGE_CODE_ENUM, nullable=False)
    asr_model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    gate_status: Mapped[str] = mapped_column(String(32), nullable=False)
    transcript_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text)
    confirmation_action: Mapped[str | None] = mapped_column(String(16))
    confirmed_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA_NAME}.actor.actor_id")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
