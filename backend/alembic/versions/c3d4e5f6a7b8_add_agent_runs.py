"""Add agent_runs table (Phase 3 observability).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("trigger_event_type", sa.String(80), nullable=True),
        sa.Column("model_provider", sa.String(20), nullable=True),
        sa.Column("model_name", sa.String(80), nullable=True),
        sa.Column("proposals", sa.Integer, nullable=False, server_default="0"),
        sa.Column("auto_executed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("queued_for_approval", sa.Integer, nullable=False, server_default="0"),
        sa.Column("decisions", sa.JSON, nullable=True),
        sa.Column("tools_requested", sa.JSON, nullable=True),
        sa.Column("verification", sa.JSON, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_agent_runs_business_created", "agent_runs", ["business_id", "created_at"])
    op.create_index("idx_agent_runs_agent", "agent_runs", ["agent_type", "created_at"])


def downgrade() -> None:
    op.drop_table("agent_runs")
