"""Add per-line partial-receipt tracking to purchase_orders (Phase 1, A6).

Adds `received_items_json` (JSON keyed by item_id -> received_qty) so the
canonical confirmed-inbound service can count ONLY the remaining
(`qty - received`) quantity as still-expected inbound for a partially-received
PO, instead of (a) counting the full PO or (b) excluding it entirely.

Revision ID: ff03_po_received_items
Revises: ff02_constraint_blocks
"""
from alembic import op
import sqlalchemy as sa

revision = "ff03_po_received_items"
down_revision = "ff02_constraint_blocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchase_orders",
        sa.Column("received_items_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("purchase_orders", "received_items_json")
