"""Add business_goals and learned_outcomes tables (Phase 4).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_goals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("metric", sa.String(80), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False, server_default="decrease"),
        sa.Column("baseline", sa.Numeric(16, 2), nullable=True),
        sa.Column("target", sa.Numeric(16, 2), nullable=False),
        sa.Column("current_value", sa.Numeric(16, 2), nullable=True),
        sa.Column("deadline", sa.Date, nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="3"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("source", sa.String(30), nullable=False, server_default="impact_ledger"),
        sa.Column("source_key", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_business_goals_business_status", "business_goals", ["business_id", "status"])
    op.create_index("idx_business_goals_metric", "business_goals", ["business_id", "metric"])

    op.create_table(
        "learned_outcomes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_action_id", UUID(as_uuid=True), sa.ForeignKey("agent_actions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("finding_id", UUID(as_uuid=True), sa.ForeignKey("findings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(30), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="inference"),
        sa.Column("recommendation", sa.String, nullable=True),
        sa.Column("approval", sa.String(20), nullable=True),
        sa.Column("rejection_reason", sa.String, nullable=True),
        sa.Column("execution_result", sa.JSON, nullable=True),
        sa.Column("verification_result", sa.JSON, nullable=True),
        sa.Column("expected_impact_sar", sa.Numeric(14, 2), nullable=True),
        sa.Column("actual_impact_sar", sa.Numeric(14, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("evidence_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_learned_outcomes_business_type", "learned_outcomes", ["business_id", "action_type"])
    op.create_index("idx_learned_outcomes_kind", "learned_outcomes", ["business_id", "kind"])


def downgrade() -> None:
    op.drop_table("learned_outcomes")
    op.drop_table("business_goals")
