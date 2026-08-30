"""Add constraint_blocks observability table (Phase 1, P0-B)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ff02_constraint_blocks"
down_revision = "ff01_owner_const"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "constraint_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("attempted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_constraint_blocks_business", "constraint_blocks", ["business_id", "created_at"])
    op.create_index("idx_constraint_blocks_code", "constraint_blocks", ["reason_code"])


def downgrade() -> None:
    op.drop_table("constraint_blocks")
