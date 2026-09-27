"""P2A: Drop the retired Celery upload task column.

Celery (queue, Beat, USE_CELERY, app.celery_app) was fully removed in Phase 2A;
Temporal is the single production execution substrate.  ``uploaded_files`` no
longer carries a Celery task id, so drop the column and its legacy index is not
required (the column had no index).

Revision ID: ff13_drop_celery_upload_task
Revises: ff12_rls_chat_pos_sync_logs
Create Date: 2026-09-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "ff13_drop_celery_upload_task"
down_revision: Union[str, None] = "ff12_rls_chat_pos_sync_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.drop_column("uploaded_files", "celery_task_id")
    else:
        with op.batch_alter_table("uploaded_files") as batch_op:
            batch_op.drop_column("celery_task_id")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.add_column("uploaded_files", sa_column())
    else:
        with op.batch_alter_table("uploaded_files") as batch_op:
            batch_op.add_column(sa_column())


def sa_column():
    from sqlalchemy import Column, String

    return Column("celery_task_id", String(), nullable=True)