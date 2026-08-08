"""Add Phase 6 Learning Engine tables.

Revision ID: d3e7a8c9b10e
Revises: c6a487f9ec1e
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = 'd3e7a8c9b10e'
down_revision: Union[str, None] = 'c6a487f9ec1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "nazmos_app"


def upgrade() -> None:
    op.create_table(
        "outcome_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_id", UUID(as_uuid=True), sa.ForeignKey("intelligence_decisions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("execution_job_id", UUID(as_uuid=True), sa.ForeignKey("execution_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_type", sa.String(50), nullable=True),
        sa.Column("predicted_outcome", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("actual_outcome", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("delta", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("feedback_source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_outcome_feedback_business_type", "outcome_feedback", ["business_id", "decision_type"])
    op.create_index("idx_outcome_feedback_decision", "outcome_feedback", ["decision_id"])
    op.create_index("idx_outcome_feedback_recorded", "outcome_feedback", ["business_id", "recorded_at"])

    op.create_table(
        "model_performance",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_type", sa.String(50), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("samples", sa.Integer, nullable=False, server_default="0"),
        sa.Column("accuracy", sa.Numeric(5, 4), nullable=True),
        sa.Column("roi_error", sa.Numeric(12, 4), nullable=True),
        sa.Column("mean_latency_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_model_performance_business_type", "model_performance", ["business_id", "decision_type"])
    op.create_index("idx_model_performance_window", "model_performance", ["business_id", "decision_type", "window_start", "window_end"])
    op.create_unique_constraint("uq_model_performance_window", "model_performance", ["business_id", "decision_type", "window_start"])

    # Enable RLS on the new business-scoped tables and grant the app role.
    from sqlalchemy import text
    for table in ("outcome_feedback", "model_performance"):
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
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE outcome_feedback TO {APP_ROLE}';
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE model_performance TO {APP_ROLE}';
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
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE outcome_feedback FROM {APP_ROLE}';
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE model_performance FROM {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )
    for table in ("outcome_feedback", "model_performance"):
        op.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_constraint("uq_model_performance_window", "model_performance", type_="unique")
    op.drop_index("idx_model_performance_window", table_name="model_performance")
    op.drop_index("idx_model_performance_business_type", table_name="model_performance")
    op.drop_table("model_performance")

    op.drop_index("idx_outcome_feedback_recorded", table_name="outcome_feedback")
    op.drop_index("idx_outcome_feedback_decision", table_name="outcome_feedback")
    op.drop_index("idx_outcome_feedback_business_type", table_name="outcome_feedback")
    op.drop_table("outcome_feedback")
