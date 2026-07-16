"""Money Audit production tables

Revision ID: 006
Revises: 005
Create Date: 2026-07-15

Persists founder-reviewable Money Audits and approval-ready recovery actions.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "money_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), server_default="generated", nullable=True),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("money_at_risk_sar", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("dead_stock_value_sar", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("stockout_risk_value_sar", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("margin_leakage_sar", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("overstock_value_sar", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("money_approved_sar", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("money_recovered_sar", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("data_quality_score", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("missing_data", postgresql.JSONB, nullable=True),
        sa.Column("summary", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_money_audits_business_created", "money_audits", ["business_id", "created_at"])
    op.create_index("idx_money_audits_status", "money_audits", ["status"])

    op.create_table(
        "money_audit_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("money_audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("priority", sa.Integer, server_default="3"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("expected_recovery_sar", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=True),
        sa.Column("recommended_discount_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("status", sa.String(30), server_default="suggested"),
        sa.Column("approval_channel", sa.String(30), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_value_sar", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("evidence", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_money_audit_actions_audit", "money_audit_actions", ["audit_id"])
    op.create_index("idx_money_audit_actions_business_status", "money_audit_actions", ["business_id", "status"])
    op.create_index("idx_money_audit_actions_item", "money_audit_actions", ["item_id"])


def downgrade() -> None:
    op.drop_index("idx_money_audit_actions_item", table_name="money_audit_actions")
    op.drop_index("idx_money_audit_actions_business_status", table_name="money_audit_actions")
    op.drop_index("idx_money_audit_actions_audit", table_name="money_audit_actions")
    op.drop_table("money_audit_actions")
    op.drop_index("idx_money_audits_status", table_name="money_audits")
    op.drop_index("idx_money_audits_business_created", table_name="money_audits")
    op.drop_table("money_audits")
