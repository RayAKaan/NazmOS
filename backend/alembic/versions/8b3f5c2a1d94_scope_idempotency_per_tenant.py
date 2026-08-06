"""scope idempotency cache per tenant

Revision ID: 8b3f5c2a1d94
Revises: e01776a29060
Create Date: 2026-08-06

Adds ``business_id`` to the idempotency cache scope so a cached response for
one tenant can never be replayed by a different tenant that happens to reuse
the same ``Idempotency-Key`` on the same path. Tenant-less requests (auth,
webhooks) are backfilled to a zero-UUID sentinel so the unique constraint still
holds and they keep a single shared scope.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = "8b3f5c2a1d94"
down_revision: Union[str, None] = "e01776a29060"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

# Matches NO_TENANT in app/middleware/idempotency.py.
NO_TENANT = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.add_column(
        "idempotency_keys",
        sa.Column("business_id", UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE idempotency_keys SET business_id = :sentinel WHERE business_id IS NULL"
        ).bindparams(sentinel=NO_TENANT)
    )
    op.drop_constraint("uq_idempotency_scope", "idempotency_keys", type_="unique")
    op.drop_index("idx_idempotency_key_lookup", table_name="idempotency_keys")
    op.create_unique_constraint(
        "uq_idempotency_scope",
        "idempotency_keys",
        ["business_id", "idempotency_key", "scope_method", "scope_path"],
    )
    op.create_index(
        "idx_idempotency_key_lookup",
        "idempotency_keys",
        ["business_id", "idempotency_key", "scope_method", "scope_path"],
    )


def downgrade() -> None:
    op.drop_index("idx_idempotency_key_lookup", table_name="idempotency_keys")
    op.drop_constraint("uq_idempotency_scope", "idempotency_keys", type_="unique")
    op.create_unique_constraint(
        "uq_idempotency_scope",
        "idempotency_keys",
        ["idempotency_key", "scope_method", "scope_path"],
    )
    op.create_index(
        "idx_idempotency_key_lookup",
        "idempotency_keys",
        ["idempotency_key", "scope_method", "scope_path"],
    )
    op.drop_column("idempotency_keys", "business_id")
