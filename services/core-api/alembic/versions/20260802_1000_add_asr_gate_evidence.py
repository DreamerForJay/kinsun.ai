"""add consent-safe, exactly-once ASR gate evidence

Revision ID: e4f7a9c2d1b3
Revises: 9b2e4c6d8f10
Create Date: 2026-08-02 10:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4f7a9c2d1b3"
down_revision: str | Sequence[str] | None = "9b2e4c6d8f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.drop_constraint(
        "conversation_session_state_check",
        "conversation_session",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "conversation_session_state_check",
        "conversation_session",
        "state IN ('CREATED','RECORDING','AWAITING_CONFIRMATION','PROCESSING','RESPONDING','COMPLETED','CANCELLED','FAILED')",
        schema=SCHEMA,
    )
    op.create_table(
        "asr_gate_evidence",
        sa.Column(
            "asr_gate_evidence_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("elder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "language_route",
            postgresql.ENUM(name="language_code_enum", schema=SCHEMA, create_type=False),
            nullable=False,
        ),
        sa.Column("asr_model_version", sa.String(length=160), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("gate_status", sa.String(length=32), nullable=False),
        sa.Column("transcript_digest", sa.String(length=64), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("confirmation_action", sa.String(length=16), nullable=True),
        sa.Column("confirmed_by_actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_asr_gate_confidence"),
        sa.CheckConstraint(
            "gate_status IN ('ALLOWED','AWAITING_CONFIRMATION','CONFIRMED','REJECTED')",
            name="ck_asr_gate_status",
        ),
        sa.CheckConstraint(
            "transcript_digest ~ '^[0-9a-f]{64}$'", name="ck_asr_gate_transcript_digest"
        ),
        sa.CheckConstraint(
            "confirmation_action IS NULL OR confirmation_action IN ('CONFIRM','REJECT')",
            name="ck_asr_gate_confirmation_action",
        ),
        sa.CheckConstraint(
            "(gate_status IN ('ALLOWED','AWAITING_CONFIRMATION') AND confirmation_action IS NULL AND confirmed_by_actor_id IS NULL AND confirmed_at IS NULL) OR (gate_status = 'CONFIRMED' AND confirmation_action = 'CONFIRM' AND confirmed_by_actor_id IS NOT NULL AND confirmed_at IS NOT NULL) OR (gate_status = 'REJECTED' AND confirmation_action = 'REJECT' AND confirmed_by_actor_id IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_asr_gate_confirmation_consistency",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenant.tenant_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["session_id"], [f"{SCHEMA}.conversation_session.session_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["elder_id"], [f"{SCHEMA}.elder.elder_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["confirmed_by_actor_id"], [f"{SCHEMA}.actor.actor_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("asr_gate_evidence_id"),
        sa.UniqueConstraint("session_id", name="uq_asr_gate_evidence_session"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_asr_gate_evidence_tenant_elder",
        "asr_gate_evidence",
        ["tenant_id", "elder_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM eldercare_ai.conversation_session
            WHERE state = 'AWAITING_CONFIRMATION'
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade while AWAITING_CONFIRMATION sessions exist';
          END IF;
        END
        $$;
        """
    )
    op.drop_index(
        "ix_asr_gate_evidence_tenant_elder", table_name="asr_gate_evidence", schema=SCHEMA
    )
    op.drop_table("asr_gate_evidence", schema=SCHEMA)
    op.drop_constraint(
        "conversation_session_state_check",
        "conversation_session",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "conversation_session_state_check",
        "conversation_session",
        "state IN ('CREATED','RECORDING','PROCESSING','RESPONDING','COMPLETED','CANCELLED','FAILED')",
        schema=SCHEMA,
    )
