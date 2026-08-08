"""Add knowledge graph engine tables.

Revision ID: efab679a4d16
Revises: bc6893878598
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.database.types import UUID


# revision identifiers, used by Alembic.
revision: str = 'efab679a4d16'
down_revision: Union[str, None] = 'bc6893878598'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "nazmos_app"


def upgrade() -> None:
    op.create_table(
        "graph_entities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("attributes", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("vector", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_graph_entities_business_type", "graph_entities", ["business_id", "entity_type"])
    op.create_index("idx_graph_entities_name", "graph_entities", ["business_id", "name"])
    op.create_unique_constraint(
        "uq_graph_entity_business_type_ext",
        "graph_entities",
        ["business_id", "entity_type", "external_id"],
    )

    op.create_table(
        "graph_relationships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), sa.ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("strength", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("evidence_event_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_graph_relationships_source", "graph_relationships", ["source_id"])
    op.create_index("idx_graph_relationships_target", "graph_relationships", ["target_id"])
    op.create_index("idx_graph_relationships_business_type", "graph_relationships", ["business_id", "relation_type"])
    op.create_unique_constraint(
        "uq_graph_relationship_edge",
        "graph_relationships",
        ["business_id", "source_id", "target_id", "relation_type"],
    )

    # Enable RLS on the new business-scoped tables and grant the app role.
    from sqlalchemy import text
    for table in ("graph_entities", "graph_relationships"):
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
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE graph_entities TO {APP_ROLE}';
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE graph_relationships TO {APP_ROLE}';
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
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE graph_entities FROM {APP_ROLE}';
                    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE graph_relationships FROM {APP_ROLE}';
                END IF;
            END
            $$;
            """
        )
    )
    for table in ("graph_entities", "graph_relationships"):
        op.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        op.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("idx_graph_relationships_business_type", table_name="graph_relationships")
    op.drop_index("idx_graph_relationships_target", table_name="graph_relationships")
    op.drop_index("idx_graph_relationships_source", table_name="graph_relationships")
    op.drop_constraint("uq_graph_relationship_edge", "graph_relationships")
    op.drop_table("graph_relationships")

    op.drop_index("idx_graph_entities_name", table_name="graph_entities")
    op.drop_index("idx_graph_entities_business_type", table_name="graph_entities")
    op.drop_constraint("uq_graph_entity_business_type_ext", "graph_entities")
    op.drop_table("graph_entities")
