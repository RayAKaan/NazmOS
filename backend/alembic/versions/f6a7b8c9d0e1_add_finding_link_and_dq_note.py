"""Add agent_actions.finding_id + learned_outcomes.data_quality_note (Phase 6).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_actions", sa.Column("finding_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_agent_actions_finding", "agent_actions", "findings", ["finding_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_agent_actions_finding_id", "agent_actions", ["finding_id"])

    op.add_column("learned_outcomes", sa.Column("data_quality_note", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("learned_outcomes", "data_quality_note")
    op.drop_index("ix_agent_actions_finding_id", table_name="agent_actions")
    op.drop_constraint("fk_agent_actions_finding", "agent_actions", type_="foreignkey")
    op.drop_column("agent_actions", "finding_id")
