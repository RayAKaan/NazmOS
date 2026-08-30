"""Add durable pilot baseline snapshots (Phase 6)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "phase6_pilot_baseline"
down_revision = "ff03_po_received_items"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "pilot_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_pilot_baseline_business", "pilot_baselines", ["business_id", "is_active"])

def downgrade():
    op.drop_index("idx_pilot_baseline_business", table_name="pilot_baselines")
    op.drop_table("pilot_baselines")
