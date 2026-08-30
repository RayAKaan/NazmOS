"""Add goal_progress_history + learned_outcomes unique constraint (Phase 5).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "goal_progress_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("goal_id", UUID(as_uuid=True), sa.ForeignKey("business_goals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measured_value", sa.Numeric(16, 2), nullable=False),
        sa.Column("progress_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("trajectory", sa.String(20), nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="scheduled"),
        sa.Column("data_quality_note", sa.String, nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_goal_history_goal_time", "goal_progress_history", ["goal_id", "measured_at"])
    op.create_unique_constraint("uq_goal_history_goal_time", "goal_progress_history", ["goal_id", "measured_at"])
    op.create_unique_constraint("uq_learned_outcome_action", "learned_outcomes", ["agent_action_id"])


def downgrade() -> None:
    op.drop_constraint("uq_learned_outcome_action", "learned_outcomes", type_="unique")
    op.drop_table("goal_progress_history")
