"""Phase A isolation core: AI reasoning request + security event audit tables.

The AI path (LLM/OpenCode) never receives raw merchant data; every request is
a signed ReasoningCapsule. These tables make each request auditable and replay
detection possible. No prompt text or capsule payload is persisted -- only the
capsule fingerprint, capability, purpose, expiry and outcome.

Revision ID: ff05_ai_isolation
Revises: ff04_forecast_provenance
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ff05_ai_isolation"
down_revision: Union[str, None] = "ff04_forecast_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type(dialect: str):
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID
        return UUID(as_uuid=True)
    return sa.String(length=36)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    uid = _uuid_type(dialect)

    op.create_table(
        "ai_reasoning_requests",
        sa.Column("id", uid, primary_key=True),
        sa.Column("business_id", uid, nullable=True),
        sa.Column("capsule_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("capsule_hash", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("purpose", sa.String(length=120), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="requested"),
        sa.Column("decision", sa.String(length=30), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_ai_req_capsule", "ai_reasoning_requests", ["capsule_id"])
    op.create_index("idx_ai_req_business", "ai_reasoning_requests", ["business_id"])
    if dialect == "postgresql":
        op.create_index("uq_ai_req_nonce", "ai_reasoning_requests", ["nonce"], unique=True)
    else:
        op.create_index("idx_ai_req_nonce", "ai_reasoning_requests", ["nonce"])

    op.create_table(
        "security_events",
        sa.Column("id", uid, primary_key=True),
        sa.Column("business_id", uid, nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=True),
        sa.Column("capsule_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_security_events_type", "security_events", ["event_type"])
    op.create_index("idx_security_events_business", "security_events", ["business_id"])
    op.create_index("idx_security_events_capsule", "security_events", ["capsule_id"])


def downgrade() -> None:
    op.drop_table("security_events")
    op.drop_table("ai_reasoning_requests")