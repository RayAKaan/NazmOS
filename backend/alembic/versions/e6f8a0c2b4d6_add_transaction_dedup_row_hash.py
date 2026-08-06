"""add transaction dedup row hash

Revision ID: e6f8a0c2b4d6
Revises: c4d6e8f0a2b1
Create Date: 2026-08-06

Adds ``transactions.row_hash`` with a partial unique index on
``(business_id, row_hash) WHERE row_hash IS NOT NULL`` so ETL re-imports of
the same file are idempotent.  Existing rows (and rows inserted by POS webhook
flows that do not compute a hash) have NULL row_hash and are exempt from the
uniqueness.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f8a0c2b4d6"
down_revision: Union[str, None] = "c4d6e8f0a2b1"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("row_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_transactions_row_hash",
        "transactions",
        ["business_id", "row_hash"],
        unique=True,
        postgresql_where=sa.text("row_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_transactions_row_hash", table_name="transactions")
    op.drop_column("transactions", "row_hash")
