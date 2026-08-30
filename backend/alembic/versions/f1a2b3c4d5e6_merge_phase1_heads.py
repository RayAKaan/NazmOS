"""Merge the two pre-existing heads before the Phase 1 agentic-foundation migration.

Revision ID: f1a2b3c4d5e6
Revises: 9fe320efe5ff, b7c8d9e0f1a2
Create Date: 2026-08-19

The migration graph had two heads (9fe320efe5ff and b7c8d9e0f1a2). This empty
merge revision reunifies them so the Phase 1 tables migration has a single
down_revision. No schema change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = ('9fe320efe5ff', 'b7c8d9e0f1a2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
