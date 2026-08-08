"""Add performance indexes for hot query paths.

Revision ID: 7597266ca47a
Revises: fbcd840f72b7
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7597266ca47a"
down_revision: Union[str, None] = "fbcd840f72b7"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Agent attention feed: filter by business + status, sort by priority/created.
    op.create_index(
        "idx_agent_actions_business_status_priority",
        "agent_actions",
        ["business_id", "status", "priority"],
    )
    op.create_index(
        "idx_agent_actions_business_status_created",
        "agent_actions",
        ["business_id", "status", "created_at"],
    )

    # Money Audit actions: pending actions are the most queried.
    op.create_index(
        "idx_money_audit_actions_business_status_priority",
        "money_audit_actions",
        ["business_id", "status", "priority"],
    )
    op.create_index(
        "idx_money_audit_actions_status_suggested",
        "money_audit_actions",
        ["business_id", "status"],
        postgresql_where=sa.text("status = 'suggested'"),
    )

    # Inventory lookups by SKU/barcode across businesses.
    op.create_index(
        "idx_items_business_sku",
        "items",
        ["business_id", "sku"],
    )
    op.create_index(
        "idx_items_business_barcode",
        "items",
        ["business_id", "barcode"],
    )

    # Transaction analytics by business + date range.
    op.create_index(
        "idx_transactions_business_date_brin",
        "transactions",
        ["business_id", "transaction_at"],
        postgresql_using="brin",
    )

    # Uploaded files: recently completed/failed for ops console.
    op.create_index(
        "idx_uploaded_files_business_status_created",
        "uploaded_files",
        ["business_id", "status", "created_at"],
    )

    # Audit log: time-series lookups by business and time.
    op.create_index(
        "idx_audit_log_business_created_brin",
        "audit_log",
        ["business_id", "created_at"],
        postgresql_using="brin",
    )


def downgrade() -> None:
    op.drop_index("idx_audit_log_business_created_brin", table_name="audit_log")
    op.drop_index("idx_uploaded_files_business_status_created", table_name="uploaded_files")
    op.drop_index("idx_transactions_business_date_brin", table_name="transactions")
    op.drop_index("idx_items_business_barcode", table_name="items")
    op.drop_index("idx_items_business_sku", table_name="items")
    op.drop_index("idx_money_audit_actions_status_suggested", table_name="money_audit_actions")
    op.drop_index("idx_money_audit_actions_business_status_priority", table_name="money_audit_actions")
    op.drop_index("idx_agent_actions_business_status_created", table_name="agent_actions")
    op.drop_index("idx_agent_actions_business_status_priority", table_name="agent_actions")
