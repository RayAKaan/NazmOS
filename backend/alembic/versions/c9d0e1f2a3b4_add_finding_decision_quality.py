"""Add findings.urgency + findings.data_quality_score (Phase 9).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("urgency", sa.String(10), nullable=True))
    op.add_column("findings", sa.Column("data_quality_score", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("findings", "data_quality_score")
    op.drop_column("findings", "urgency")
