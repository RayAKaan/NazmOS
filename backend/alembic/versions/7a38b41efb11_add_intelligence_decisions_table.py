"""Add intelligence decisions table.

Revision ID: 7a38b41efb11
Revises: 357f3cbca428
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = '7a38b41efb11'
down_revision: Union[str, None] = '357f3cbca428'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "nazmos_app"


def upgrade() -> None:
    op.create_table(
        "intelligence_decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_type", sa.String(50), nullable=False),
        sa.Column("input_event_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("rules_applied", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("memory_snapshot", sa.JSON, nullable=True),
        sa.Column("graph_evidence", sa.JSON, nullable=True),
        sa.Column("context_evidence", sa.JSON, nullable=True),
        sa.Column("candidate_actions", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("ranked_action", sa.JSON, nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.0"),
        sa.Column("expected_roi", sa.Numeric(12, 2), nullable=True),
        sa.Column("risk_score", sa.Numeric(4, 3), nullable=False, server_default="0.0"),
        sa.Column("urgency", sa.Numeric(4, 3), nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("explanation", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_intelligence_decisions_business", "intelligence_decisions", ["business_id", "created_at"])
    op.create_index("idx_intelligence_decisions_status", "intelligence_decisions", ["business_id", "status"])
    op.create_index("idx_intelligence_decisions_type", "intelligence_decisions", ["business_id", "decision_type"])

    # Enable RLS on the new business-scoped table and grant the app role.
    from sqlalchemy import text
    op.execute(text("ALTER TABLE intelligence_decisions ENABLE ROW LEVEL SECURITY"))
    op.execute(text("DROP POLICY IF EXISTS intelligence_decisions_tenant_isolation ON intelligence_decisions"))
    op.execute(text(
        "CREATE POLICY intelligence_decisions_tenant_isolation ON intelligence_decisions "
        "FOR ALL USING (business_id = app.current_tenant_id()) "
        "WITH CHECK (business_id = app.current_tenant_id())"
    ))

    op.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE intelligence_decisions TO {APP_ROLE}';
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
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE intelligence_decisions FROM {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )
    op.execute(text("DROP POLICY IF EXISTS intelligence_decisions_tenant_isolation ON intelligence_decisions"))
    op.execute(text("ALTER TABLE intelligence_decisions DISABLE ROW LEVEL SECURITY"))

    op.drop_index("idx_intelligence_decisions_type", table_name="intelligence_decisions")
    op.drop_index("idx_intelligence_decisions_status", table_name="intelligence_decisions")
    op.drop_index("idx_intelligence_decisions_business", table_name="intelligence_decisions")
    op.drop_table("intelligence_decisions")
