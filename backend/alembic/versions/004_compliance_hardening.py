"""Retail guardrails: Shariah item screening state

Revision ID: 004
Revises: 003
Create Date: 2026-07-06 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GENESIS_PIH = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="


def upgrade() -> None:
    # Item-level Shariah screening state for import/POS/manual flows.
    op.add_column("items", sa.Column("shariah_status", sa.String(30), server_default="unknown"))
    op.add_column("items", sa.Column("shariah_flags", postgresql.JSONB, nullable=True))
    op.add_column("items", sa.Column("shariah_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_items_shariah_status", "items", ["business_id", "shariah_status"])


def downgrade() -> None:
    op.drop_index("idx_items_shariah_status", table_name="items")
    op.drop_column("items", "shariah_checked_at")
    op.drop_column("items", "shariah_flags")
    op.drop_column("items", "shariah_status")
