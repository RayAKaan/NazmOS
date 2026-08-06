"""Add webhook_events table for POS webhook audit and replay.

Revision ID: 7599266ca47c
Revises: 7598266ca47b
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = "7599266ca47c"
down_revision: Union[str, None] = "7598266ca47b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=True),
        sa.Column("external_event_id", sa.String(255), nullable=True, index=True),
        sa.Column("signature_valid", sa.Boolean, nullable=False, default=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, default="received"),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_webhook_events_business_created", "webhook_events", ["business_id", "created_at"])
    op.create_index("idx_webhook_events_status", "webhook_events", ["status", "created_at"])
    op.create_unique_constraint("uq_webhook_events_provider_external_id", "webhook_events", ["provider", "external_event_id"])


def downgrade() -> None:
    op.drop_constraint("uq_webhook_events_provider_external_id", "webhook_events")
    op.drop_index("idx_webhook_events_status", table_name="webhook_events")
    op.drop_index("idx_webhook_events_business_created", table_name="webhook_events")
    op.drop_table("webhook_events")
