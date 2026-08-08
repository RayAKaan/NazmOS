"""Add business memory engine tables.

Revision ID: bc6893878598
Revises: 969ef7949298
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = 'bc6893878598'
down_revision: Union[str, None] = '969ef7949298'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "nazmos_app"


def upgrade() -> None:
    op.create_table(
        "business_memory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_type", sa.String(50), nullable=False),
        sa.Column("data", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_by_event_id", UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_business_memory_business_type", "business_memory", ["business_id", "memory_type"])
    op.create_index("idx_business_memory_updated", "business_memory", ["business_id", "updated_at"])
    op.create_unique_constraint(
        "uq_business_memory_business_type",
        "business_memory",
        ["business_id", "memory_type"],
    )

    op.create_table(
        "memory_updates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_type", sa.String(50), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("old_value", sa.JSON, nullable=True),
        sa.Column("new_value", sa.JSON, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_memory_updates_business_type", "memory_updates", ["business_id", "memory_type"])
    op.create_index("idx_memory_updates_event", "memory_updates", ["event_id"])
    op.create_index("idx_memory_updates_occurred", "memory_updates", ["business_id", "occurred_at"])

    # Enable RLS on the new business-scoped tables and grant the app role.
    from sqlalchemy import text
    for table in ("business_memory", "memory_updates"):
        op.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(text(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING (business_id = app.current_tenant_id()) "
            f"WITH CHECK (business_id = app.current_tenant_id())"
        ))

    op.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE business_memory TO {APP_ROLE}';
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE memory_updates TO {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    from sqlalchemy import text
    op.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE business_memory FROM {APP_ROLE}';
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE memory_updates FROM {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )
    for table in ("business_memory", "memory_updates"):
        op.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("idx_memory_updates_occurred", table_name="memory_updates")
    op.drop_index("idx_memory_updates_event", table_name="memory_updates")
    op.drop_index("idx_memory_updates_business_type", table_name="memory_updates")
    op.drop_table("memory_updates")

    op.drop_constraint("uq_business_memory_business_type", "business_memory")
    op.drop_index("idx_business_memory_updated", table_name="business_memory")
    op.drop_index("idx_business_memory_business_type", table_name="business_memory")
    op.drop_table("business_memory")
