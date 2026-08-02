"""add elder UI memory confirmation evidence

Revision ID: 9b2e4c6d8f10
Revises: c1a9e7f24b63
Create Date: 2026-08-02 09:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "9b2e4c6d8f10"
down_revision: str | Sequence[str] | None = "c1a9e7f24b63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_memory_confirmation_method",
        "memory",
        schema="eldercare_ai",
        type_="check",
    )
    op.create_check_constraint(
        "ck_memory_confirmation_method",
        "memory",
        "confirmation_method IS NULL OR confirmation_method IN "
        "('VOICE', 'ELDER_UI', 'CAREGIVER_REVIEW', 'LEGAL_REPRESENTATIVE')",
        schema="eldercare_ai",
    )
    op.create_check_constraint(
        "ck_memory_elder_ui_confirmation_evidence",
        "memory",
        "confirmation_method <> 'ELDER_UI' OR "
        "(confirmation_session_id IS NULL AND confirmation_evidence_ref IS NOT NULL)",
        schema="eldercare_ai",
    )


def downgrade() -> None:
    # Never silently relabel or erase formal confirmation evidence. An operator
    # must migrate/deactivate ELDER_UI rows explicitly before downgrading.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM eldercare_ai.memory
            WHERE confirmation_method = 'ELDER_UI'
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade while ELDER_UI memory confirmations exist';
          END IF;
        END
        $$;
        """
    )
    op.drop_constraint(
        "ck_memory_elder_ui_confirmation_evidence",
        "memory",
        schema="eldercare_ai",
        type_="check",
    )
    op.drop_constraint(
        "ck_memory_confirmation_method",
        "memory",
        schema="eldercare_ai",
        type_="check",
    )
    op.create_check_constraint(
        "ck_memory_confirmation_method",
        "memory",
        "confirmation_method IS NULL OR confirmation_method IN "
        "('VOICE', 'CAREGIVER_REVIEW', 'LEGAL_REPRESENTATIVE')",
        schema="eldercare_ai",
    )
