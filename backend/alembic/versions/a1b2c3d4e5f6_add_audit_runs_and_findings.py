"""Add AuditRun and Finding tables (Phase 1 agentic foundation).

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("trigger_event_type", sa.String(80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.JSON, nullable=True),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_audit_runs_business_domain", "audit_runs", ["business_id", "domain", "created_at"])
    op.create_index("idx_audit_runs_status", "audit_runs", ["status"])

    op.create_table(
        "findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audit_id", UUID(as_uuid=True), sa.ForeignKey("audit_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("explanation", sa.String, nullable=True),
        sa.Column("evidence", sa.JSON, nullable=True),
        sa.Column("affected_entities", sa.JSON, nullable=True),
        sa.Column("estimated_financial_impact_sar", sa.Numeric(14, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 2), nullable=True),
        sa.Column("recommended_action", sa.JSON, nullable=True),
        sa.Column("action_risk", sa.String(20), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="detected"),
        sa.Column("verification_result", sa.JSON, nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="audit_engine"),
        sa.Column("agent_action_id", UUID(as_uuid=True), sa.ForeignKey("agent_actions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_findings_business_status", "findings", ["business_id", "status"])
    op.create_index("idx_findings_audit", "findings", ["audit_id"])
    op.create_index("idx_findings_domain_severity", "findings", ["domain", "severity"])


def downgrade() -> None:
    op.drop_table("findings")
    op.drop_table("audit_runs")
