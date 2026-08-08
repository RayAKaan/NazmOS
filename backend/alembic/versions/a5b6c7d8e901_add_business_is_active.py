"""Add is_active to businesses for GDPR/PDPL soft-deletion.

Revision ID: a5b6c7d8e901
Revises: 9fe320efe5ff
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e901"
down_revision: Union[str, None] = "9fe320efe5ff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("businesses", "is_active")