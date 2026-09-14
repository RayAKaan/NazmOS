"""P0: RLS for the join-scoped tenant tables chat_messages + pos_sync_logs.

chat_messages carries no business_id column; it belongs to a tenant through
chat_sessions.session_id.  pos_sync_logs belongs to a tenant through
pos_connections.connection_id.  Both parents already carry the standard
``business_id = app.current_tenant_id()`` policy, so the child tables get a
join-based policy that resolves the tenant through the parent instead of
denormalizing a second tenant column.

Because ``app.current_tenant_id()`` is NULL outside an authenticated tenant
context, both policies evaluate to false (no rows visible/written), preserving
the fail-closed behaviour of the rest of the RLS surface.

Revision ID: ff12_rls_chat_pos_sync_logs
Revises: ff11_full_schema_app_role_grants
Create Date: 2026-09-13
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "ff12_rls_chat_pos_sync_logs"
down_revision: Union[str, None] = "ff11_full_schema_app_role_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "nazmos_app"

# table -> (child FK column, parent tenant table)
JOIN_POLICIES = {
    "chat_messages": ("session_id", "chat_sessions"),
    "pos_sync_logs": ("connection_id", "pos_connections"),
}


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    for table, (child_col, parent_table) in JOIN_POLICIES.items():
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        )
        conn.execute(
            text(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                    FOR ALL
                    USING ({child_col} IN (
                        SELECT id FROM {parent_table}
                        WHERE business_id = app.current_tenant_id()
                    ))
                    WITH CHECK ({child_col} IN (
                        SELECT id FROM {parent_table}
                        WHERE business_id = app.current_tenant_id()
                    ))
                """
            )
        )

    grants = ", ".join(JOIN_POLICIES)
    conn.execute(text(f"GRANT {APP_ROLE} TO CURRENT_USER"))
    conn.execute(
        text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {grants} TO {APP_ROLE}")
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    for table in JOIN_POLICIES:
        conn.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))