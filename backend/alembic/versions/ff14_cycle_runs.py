"""Phase 4: durable cycle_runs table for the Business Improvement Loop.

Chains from the verified single alembic head ``ff13_drop_celery_upload_task``.
Adds the ONLY durable loop artifact for Phase 4: one row per bounded improvement
cycle (``cycle.py::CycleRun.serialize`` is the lossless durability seam). RLS +
``nazmos_app`` grants mirror the verified pattern of ``c6a487f9ec1e`` /
``b7c8d9e0f1a2`` / ``ff11``.

Revision ID: ff14_cycle_runs
Revises: ff13_drop_celery_upload_task
Create Date: 2026-09-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = "ff14_cycle_runs"
down_revision: Union[str, None] = "ff13_drop_celery_upload_task"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "nazmos_app"


def upgrade() -> None:
    op.create_table(
        "cycle_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trigger", sa.String(64), nullable=False),
        sa.Column("trigger_token", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("starting_state_version", sa.String(64), nullable=True),
        sa.Column("evidence_watermark", sa.String(64), nullable=True),
        sa.Column("stage_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("last_error", sa.Text, nullable=False, server_default=""),
        sa.Column("state_output", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("stages", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("schema_version", sa.String(16), nullable=False, server_default="loop-v1"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("stage_index >= 0", name="ck_cycle_runs_stage_index_nonneg"),
    )
    op.create_unique_constraint(
        "uq_cycle_runs_business_cycle", "cycle_runs", ["business_id", "cycle_id"]
    )
    op.create_index(
        "idx_cycle_runs_tenant_lookup", "cycle_runs", ["business_id", "created_at"]
    )

    # RLS on the same business_id policy as every tenant table.
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text("ALTER TABLE cycle_runs ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text("DROP POLICY IF EXISTS cycle_runs_tenant_isolation ON cycle_runs"))
        conn.execute(sa.text(
            "CREATE POLICY cycle_runs_tenant_isolation ON cycle_runs "
            "FOR ALL USING (business_id = app.current_tenant_id()) "
            "WITH CHECK (business_id = app.current_tenant_id())"
        ))
        conn.execute(sa.text(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nazmos_app') THEN "
            "EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE cycle_runs TO nazmos_app'; END IF; END $$;"
        ))


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nazmos_app') THEN "
            "EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE cycle_runs FROM nazmos_app'; END IF; END $$;"
        ))
        conn.execute(sa.text("DROP POLICY IF EXISTS cycle_runs_tenant_isolation ON cycle_runs"))
        conn.execute(sa.text("ALTER TABLE cycle_runs DISABLE ROW LEVEL SECURITY"))
    op.drop_index("idx_cycle_runs_tenant_lookup", table_name="cycle_runs")
    op.drop_constraint("uq_cycle_runs_business_cycle", "cycle_runs", type_="unique")
    op.drop_table("cycle_runs")