"""Catch-up grant: nazmos_app on ALL existing tables + sequences.

After RLS Phase B (33dd43) only tenant tables carrying business_id were granted
to nazmos_app.  Platform/org-level tables (users, businesses, organizations,
suppliers, etc.) were created before the app-role pattern existed and were never
granted, causing ``permission denied for table users`` at runtime when the
connection sets ``SET LOCAL ROLE nazmos_app``.

This migration is idempotent-safe: the GRANTs are no-ops when already held.

Revision ID: ff11_full_schema_app_role_grants
Revises: ff10_execution_key_idempotency
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "ff11_full_schema_app_role_grants"
down_revision: Union[str, None] = "ff10_execution_key_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "nazmos_app"


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # Ensure role exists + owner can assume it.
    conn.execute(text(f"GRANT {APP_ROLE} TO CURRENT_USER"))
    conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))

    # ── tables ────────────────────────────────────────────────────────────
    conn.execute(
        text(
            f"""
            DO $$
            DECLARE t text;
            BEGIN
                FOR t IN (
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                ) LOOP
                    EXECUTE format(
                        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO {APP_ROLE}',
                        t
                    );
                END LOOP;
            END
            $$;
            """
        )
    )

    # ── sequences ─────────────────────────────────────────────────────────
    conn.execute(
        text(
            f"""
            DO $$
            DECLARE s text;
            BEGIN
                FOR s IN (
                    SELECT sequence_name FROM information_schema.sequences
                    WHERE sequence_schema = 'public'
                ) LOOP
                    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO {APP_ROLE}', s);
                END LOOP;
            END
            $$;
            """
        )
    )

    # ── default privileges: future tables owned by the migration user ─────
    conn.execute(
        text(
            f"""
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}
            """
        )
    )
    conn.execute(
        text(
            f"""
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
                GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"))
    conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"))
