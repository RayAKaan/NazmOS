"""Add impact_ledger.attribution (Phase 8).

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("impact_ledger", sa.Column("attribution", sa.String(20), nullable=False, server_default="estimated"))


def downgrade() -> None:
    op.drop_column("impact_ledger", "attribution")
