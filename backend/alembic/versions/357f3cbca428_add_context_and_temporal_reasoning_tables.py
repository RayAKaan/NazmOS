"""Add context and temporal reasoning tables.

Revision ID: 357f3cbca428
Revises: efab679a4d16
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = '357f3cbca428'
down_revision: Union[str, None] = 'efab679a4d16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "nazmos_app"


def upgrade() -> None:
    op.create_table(
        "business_context",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("context_type", sa.String(50), nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_business_context_business_type", "business_context", ["business_id", "context_type"])
    op.create_index("idx_business_context_effective", "business_context", ["business_id", "effective_from", "effective_until"])

    op.create_table(
        "event_derivations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cause_event_id", UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("effect_event_id", UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("derivation_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("evidence", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_event_derivations_effect", "event_derivations", ["effect_event_id"])
    op.create_index("idx_event_derivations_cause", "event_derivations", ["cause_event_id"])
    op.create_unique_constraint(
        "uq_event_derivation",
        "event_derivations",
        ["business_id", "cause_event_id", "effect_event_id", "derivation_type"],
    )

    # Enable RLS on the new business-scoped tables and grant the app role.
    from sqlalchemy import text
    for table in ("business_context", "event_derivations"):
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
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE business_context TO {APP_ROLE}';
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE event_derivations TO {APP_ROLE}';
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
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE business_context FROM {APP_ROLE}';
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE event_derivations FROM {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )
    for table in ("business_context", "event_derivations"):
        op.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("idx_event_derivations_cause", table_name="event_derivations")
    op.drop_index("idx_event_derivations_effect", table_name="event_derivations")
    op.drop_constraint("uq_event_derivation", "event_derivations")
    op.drop_table("event_derivations")

    op.drop_index("idx_business_context_effective", table_name="business_context")
    op.drop_index("idx_business_context_business_type", table_name="business_context")
    op.drop_table("business_context")
