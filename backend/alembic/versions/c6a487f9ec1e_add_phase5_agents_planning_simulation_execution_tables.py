"""Add Phase 5 agents, planning, simulation, and execution tables.

Revision ID: c6a487f9ec1e
Revises: 7a38b41efb11
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = 'c6a487f9ec1e'
down_revision: Union[str, None] = '7a38b41efb11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "nazmos_app"


def upgrade() -> None:
    op.create_table(
        "simulations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scenario", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("assumptions", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("results", sa.JSON, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_simulations_business_status", "simulations", ["business_id", "status"])
    op.create_index("idx_simulations_business_created", "simulations", ["business_id", "created_at"])

    op.create_table(
        "plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goal", sa.String(500), nullable=False),
        sa.Column("steps", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("estimated_roi", sa.Numeric(12, 2), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("estimated_duration_hours", sa.Numeric(8, 2), nullable=True),
        sa.Column("simulation_id", UUID(as_uuid=True), sa.ForeignKey("simulations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_plans_business_status", "plans", ["business_id", "status"])
    op.create_index("idx_plans_business_created", "plans", ["business_id", "created_at"])

    op.create_table(
        "execution_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_id", UUID(as_uuid=True), sa.ForeignKey("intelligence_decisions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("external_reference", sa.String(255), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_payload", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_execution_jobs_business_status", "execution_jobs", ["business_id", "status"])
    op.create_index("idx_execution_jobs_decision", "execution_jobs", ["decision_id"])
    op.create_index("idx_execution_jobs_plan", "execution_jobs", ["plan_id"])

    # Enable RLS on the new business-scoped tables and grant the app role.
    from sqlalchemy import text
    for table in ("simulations", "plans", "execution_jobs"):
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
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE simulations TO {APP_ROLE}';
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE plans TO {APP_ROLE}';
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE execution_jobs TO {APP_ROLE}';
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
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE simulations FROM {APP_ROLE}';
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE plans FROM {APP_ROLE}';
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE execution_jobs FROM {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )
    for table in ("simulations", "plans", "execution_jobs"):
        op.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("idx_execution_jobs_plan", table_name="execution_jobs")
    op.drop_index("idx_execution_jobs_decision", table_name="execution_jobs")
    op.drop_index("idx_execution_jobs_business_status", table_name="execution_jobs")
    op.drop_table("execution_jobs")

    op.drop_index("idx_plans_business_created", table_name="plans")
    op.drop_index("idx_plans_business_status", table_name="plans")
    op.drop_table("plans")

    op.drop_index("idx_simulations_business_created", table_name="simulations")
    op.drop_index("idx_simulations_business_status", table_name="simulations")
    op.drop_table("simulations")
