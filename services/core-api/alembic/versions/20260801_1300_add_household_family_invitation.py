"""add household tenant and family invitation aggregate

Revision ID: c1a9e7f24b63
Revises: e4a1c8f29b73
Create Date: 2026-08-01 13:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c1a9e7f24b63"
down_revision: str | Sequence[str] | None = "f5d9c1b7a204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Public elder onboarding creates a dedicated isolation boundary.  The
    # frozen baseline enum intentionally remains untouched; this migration is
    # the only authority that introduces the new value.
    op.execute("ALTER TYPE eldercare_ai.tenant_type_enum ADD VALUE IF NOT EXISTS 'HOUSEHOLD'")

    op.create_table(
        "family_invitation",
        sa.Column(
            "family_invitation_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eldercare_ai.tenant.tenant_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "elder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eldercare_ai.elder.elder_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "issued_by_actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eldercare_ai.actor.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invitee_email_hmac",
            sa.CHAR(length=64),
            nullable=True,
        ),
        sa.Column(
            "token_hash",
            sa.CHAR(length=64),
            nullable=False,
        ),
        sa.Column(
            "share_scope",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default=sa.text(
                "ARRAY['REPORT_DAILY','REPORT_WEEKLY','REPORT_MONTHLY']::varchar[]"
            ),
        ),
        sa.Column(
            "consent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eldercare_ai.consent_grant.consent_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'ISSUED'"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
        sa.Column(
            "redeemed_by_actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eldercare_ai.actor.actor_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('ISSUED','REDEEMED','EXPIRED','REVOKED','LOCKED')",
            name="ck_family_invitation_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
            name="ck_family_invitation_attempts",
        ),
        sa.CheckConstraint("version > 0", name="ck_family_invitation_version"),
        sa.CheckConstraint(
            "cardinality(share_scope) > 0",
            name="ck_family_invitation_share_scope_not_empty",
        ),
        sa.CheckConstraint(
            "(status = 'REDEEMED' AND redeemed_by_actor_id IS NOT NULL "
            "AND redeemed_at IS NOT NULL) "
            "OR (status <> 'REDEEMED')",
            name="ck_family_invitation_redeemed_fields",
        ),
        sa.UniqueConstraint("token_hash", name="uq_family_invitation_token_hash"),
        schema="eldercare_ai",
    )
    op.create_index(
        "idx_family_invitation_elder_status",
        "family_invitation",
        ["tenant_id", "elder_id", "status", "expires_at"],
        schema="eldercare_ai",
    )
    op.create_index(
        "idx_family_invitation_recipient",
        "family_invitation",
        ["invitee_email_hmac", "status"],
        schema="eldercare_ai",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_family_invitation_recipient",
        table_name="family_invitation",
        schema="eldercare_ai",
    )
    op.drop_index(
        "idx_family_invitation_elder_status",
        table_name="family_invitation",
        schema="eldercare_ai",
    )
    op.drop_table("family_invitation", schema="eldercare_ai")

    # PostgreSQL cannot drop one enum label directly. Rebuild the type after
    # the HOUSEHOLD rows have been removed with the table/domain downgrade.
    op.execute(
        """
        CREATE TYPE eldercare_ai.tenant_type_enum_without_household AS ENUM
          ('CARE_ORGANIZATION','COMMUNITY_ORGANIZATION','HOME_CARE_PROVIDER','DEMO');
        ALTER TABLE eldercare_ai.tenant
          ALTER COLUMN tenant_type TYPE eldercare_ai.tenant_type_enum_without_household
          USING tenant_type::text::eldercare_ai.tenant_type_enum_without_household;
        DROP TYPE eldercare_ai.tenant_type_enum;
        ALTER TYPE eldercare_ai.tenant_type_enum_without_household
          RENAME TO tenant_type_enum;
        """
    )
