"""Phase 1 (Temporal): add execution_key idempotency columns.

Execution paths (manual, agent, simulated) now carry a deterministic
SHA-256 execution key so that a replayed/idempotent execution can be
detected and skipped rather than re-applied. Three execution tables gain
an indexed nullable ``execution_key varchar(64)`` column:

  - executed_actions
  - agent_actions
  - execution_jobs

Revision ID: ff10_execution_key_idempotency
Revises: ff09_forecast_version_widen
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "ff10_execution_key_idempotency"
down_revision: Union[str, None] = "ff09_forecast_version_widen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = ["executed_actions", "agent_actions", "execution_jobs"]


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("execution_key", sa.String(length=64), nullable=True))
        op.create_index(f"ix_{table}_execution_key", table, ["execution_key"])


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_execution_key", table_name=table)
        op.drop_column(table, "execution_key")
