"""Add events and event engine tables.

Revision ID: 969ef7949298
Revises: e01776a29060
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = '969ef7949298'
down_revision: Union[str, None] = 'e01776a29060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "nazmos_app"


def upgrade() -> None:
    op.create_table(
        "event_types",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("schema", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("example", sa.JSON, nullable=True),
        sa.Column("is_system", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_event_types_name", "event_types", ["name"], unique=True)

    op.create_table(
        "event_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("consumer_name", sa.String(100), nullable=False),
        sa.Column("event_pattern", sa.String(255), nullable=False),
        sa.Column("queue_or_channel", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_event_subscriptions_pattern", "event_subscriptions", ["event_pattern"])
    op.create_index("idx_event_subscriptions_business", "event_subscriptions", ["business_id"])

    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("context_snapshot", sa.JSON, nullable=True),
        sa.Column("actor_type", sa.String(50), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("causation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed", sa.Boolean, server_default="false", index=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String, nullable=True),
    )
    op.create_index("idx_events_business_occurred", "events", ["business_id", "occurred_at"])
    op.create_index("idx_events_business_type", "events", ["business_id", "event_type"])
    op.create_index("idx_events_source_source_id", "events", ["source", "source_id"])
    op.create_index(
        "idx_events_dedupe",
        "events",
        ["business_id", "source", "source_id", "checksum"],
    )

    # Enable RLS on the new business-scoped tables and grant the app role.
    from sqlalchemy import text
    for table in ("events", "event_subscriptions"):
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
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE events TO {APP_ROLE}';
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE event_subscriptions TO {APP_ROLE}';
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
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE events FROM {APP_ROLE}';
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE event_subscriptions FROM {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )
    for table in ("events", "event_subscriptions"):
        op.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("idx_events_dedupe", table_name="events")
    op.drop_index("idx_events_source_source_id", table_name="events")
    op.drop_index("idx_events_business_type", table_name="events")
    op.drop_index("idx_events_business_occurred", table_name="events")
    op.drop_table("events")

    op.drop_index("idx_event_subscriptions_business", table_name="event_subscriptions")
    op.drop_index("idx_event_subscriptions_pattern", table_name="event_subscriptions")
    op.drop_table("event_subscriptions")

    op.drop_index("idx_event_types_name", table_name="event_types")
    op.drop_table("event_types")
