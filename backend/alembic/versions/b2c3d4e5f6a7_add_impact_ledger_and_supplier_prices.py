"""Add ImpactLedger and SupplierPrice tables (Phase 2).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "impact_ledger",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", UUID(as_uuid=True), sa.ForeignKey("findings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_action_id", UUID(as_uuid=True), sa.ForeignKey("agent_actions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("impact_type", sa.String(30), nullable=False),
        sa.Column("amount_sar", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("baseline_sar", sa.Numeric(14, 2), nullable=True),
        sa.Column("expected_sar", sa.Numeric(14, 2), nullable=True),
        sa.Column("actual_sar", sa.Numeric(14, 2), nullable=True),
        sa.Column("verification", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("evidence", sa.JSON, nullable=True),
        sa.Column("note", sa.String, nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_impact_ledger_business_type", "impact_ledger", ["business_id", "impact_type"])
    op.create_index("idx_impact_ledger_finding", "impact_ledger", ["finding_id"])

    op.create_table(
        "supplier_prices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=True),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("barcode", sa.String(100), nullable=True),
        sa.Column("unit_price_sar", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="SAR"),
        sa.Column("min_quantity", sa.Numeric(12, 2), nullable=True),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_supplier_prices_supplier_item", "supplier_prices", ["supplier_id", "item_id"])
    op.create_index("idx_supplier_prices_sku", "supplier_prices", ["sku"])


def downgrade() -> None:
    op.drop_table("supplier_prices")
    op.drop_table("impact_ledger")
