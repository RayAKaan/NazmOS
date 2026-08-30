"""Add outcome_feedback.agent_action_id + unique constraint (Phase 7).

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("outcome_feedback", sa.Column("agent_action_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_outcome_feedback_agent_action", "outcome_feedback", "agent_actions", ["agent_action_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_outcome_feedback_agent_action_id", "outcome_feedback", ["agent_action_id"])
    op.create_unique_constraint("uq_outcome_feedback_action", "outcome_feedback", ["agent_action_id"])


def downgrade() -> None:
    op.drop_constraint("uq_outcome_feedback_action", "outcome_feedback", type_="unique")
    op.drop_index("ix_outcome_feedback_agent_action_id", table_name="outcome_feedback")
    op.drop_constraint("fk_outcome_feedback_agent_action", "outcome_feedback", type_="foreignkey")
    op.drop_column("outcome_feedback", "agent_action_id")
