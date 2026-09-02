"""Phase C: field-level encryption for sensitive columns (starts users.two_factor_secret).

Converts ``users.two_factor_secret`` from plaintext VARCHAR to encrypted bytea
backed by the same Fernet master key as CredentialVault. Existing plaintext
rows are re-encrypted in-place; rows that are already Fernet tokens are left
untouched so the migration is idempotent across re-runs on partially-migrated
databases.

The ORM attribute semantics are unchanged (still a ``str``); only bytes at
rest change (app.database.encryption.EncryptedText).

Revision ID: ff06_field_encryption
Revises: ff05_ai_isolation
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.encryption import get_fernet

revision: str = "ff06_field_encryption"
down_revision: Union[str, None] = "ff05_ai_isolation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "users",
            "two_factor_secret",
            existing_type=sa.String(),
            type_=sa.LargeBinary(),
            postgresql_using="two_factor_secret::bytea",
        )
    else:
        op.alter_column("users", "two_factor_secret", existing_type=sa.String(),
                        type_=sa.LargeBinary())

    # Backfill: encrypt any remaining legacy plaintext values.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, two_factor_secret FROM users WHERE two_factor_secret IS NOT NULL")
    ).fetchall()
    fernet = get_fernet()
    for row_id, value in rows:
        raw = bytes(value) if isinstance(value, (bytes, bytearray, memoryview)) else str(value).encode("utf-8")
        try:
            fernet.decrypt(raw)
        except Exception:
            # Legacy plaintext (or SQLite text repr): re-encrypt at rest.
            conn.execute(
                sa.text("UPDATE users SET two_factor_secret = :enc WHERE id = :id"),
                {"enc": fernet.encrypt(raw), "id": row_id},
            )


def downgrade() -> None:
    # Reverse conversion is lossy when any row is still encrypted; decrypt with
    # the master key before returning to VARCHAR.
    conn = op.get_bind()
    fernet = get_fernet()
    rows = conn.execute(
        sa.text("SELECT id, two_factor_secret FROM users WHERE two_factor_secret IS NOT NULL")
    ).fetchall()
    for row_id, value in rows:
        raw = bytes(value) if isinstance(value, (bytes, bytearray, memoryview)) else str(value).encode("utf-8")
        try:
            plaintext = fernet.decrypt(raw).decode("utf-8")
        except Exception:
            plaintext = raw.decode("utf-8", errors="replace")
        conn.execute(
            sa.text("UPDATE users SET two_factor_secret = :p WHERE id = :id"),
            {"p": plaintext, "id": row_id},
        )
    op.alter_column("users", "two_factor_secret", existing_type=sa.LargeBinary(),
                    type_=sa.String())