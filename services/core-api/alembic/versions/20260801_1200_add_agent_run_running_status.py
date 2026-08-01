"""add running AgentRun status

Revision ID: f5d9c1b7a204
Revises: e4a1c8f29b73
Create Date: 2026-08-01 12:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f5d9c1b7a204"
down_revision: str | Sequence[str] | None = "e4a1c8f29b73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGENT_RUN_RESULT_STATUSES = (
    "'RUNNING','SUCCESS','NEEDS_CLARIFICATION','BLOCKED','HUMAN_REVIEW',"
    "'NO_DATA','SCHEMA_FAILED','DEPENDENCY_FAILED','TIME_BUDGET_EXCEEDED',"
    "'COST_BUDGET_EXCEEDED','CANCELLED'"
)

_AGENT_RUN_TERMINAL_STATUSES = (
    "'SUCCESS','NEEDS_CLARIFICATION','BLOCKED','HUMAN_REVIEW','NO_DATA',"
    "'SCHEMA_FAILED','DEPENDENCY_FAILED','TIME_BUDGET_EXCEEDED',"
    "'COST_BUDGET_EXCEEDED','CANCELLED'"
)


def upgrade() -> None:
    op.drop_constraint(
        "agent_run_result_status_check",
        "agent_run",
        schema="eldercare_ai",
        type_="check",
    )
    op.create_check_constraint(
        "agent_run_result_status_check",
        "agent_run",
        f"result_status IN ({_AGENT_RUN_RESULT_STATUSES})",
        schema="eldercare_ai",
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE eldercare_ai.agent_run
        SET result_status = 'CANCELLED',
            completed_at = COALESCE(completed_at, now()),
            stop_reason = COALESCE(stop_reason, 'RUNNING_STATUS_REMOVED')
        WHERE result_status = 'RUNNING'
        """
    )
    op.drop_constraint(
        "agent_run_result_status_check",
        "agent_run",
        schema="eldercare_ai",
        type_="check",
    )
    op.create_check_constraint(
        "agent_run_result_status_check",
        "agent_run",
        f"result_status IN ({_AGENT_RUN_TERMINAL_STATUSES})",
        schema="eldercare_ai",
    )
