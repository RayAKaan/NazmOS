"""Forecast provenance: add provider/data provenance columns to forecast_cache.

Hardening addition. The old rows carry no info about which path produced them
(router vs Celery vs legacy), what interval semantics their bounds have, or what
data window they were trained on. These nullable columns keep every existing row
readable while letting new rows record that provenance; existing rows are
backfilled with provider='legacy'.

Revision ID: ff04_forecast_provenance
Revises: phase_b_rls_core_services
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "ff04_forecast_provenance"
down_revision: Union[str, None] = "phase_b_rls_core_services"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    json_type = JSONB if dialect == "postgresql" else sa.JSON()

    op.add_column("forecast_cache", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("forecast_cache", sa.Column("data_start", sa.Date(), nullable=True))
    op.add_column("forecast_cache", sa.Column("data_end", sa.Date(), nullable=True))
    op.add_column("forecast_cache", sa.Column("context_days", sa.Integer(), nullable=True))
    op.add_column("forecast_cache", sa.Column("horizon_days", sa.Integer(), nullable=True))
    op.add_column("forecast_cache", sa.Column("interval_type", sa.String(length=50), nullable=True))
    op.add_column("forecast_cache", sa.Column("fallback_reason", sa.String(length=100), nullable=True))
    op.add_column("forecast_cache", sa.Column("data_quality_json", json_type, nullable=True))
    op.add_column("forecast_cache", sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill: rows written before provenance existed are marked as legacy so
    # consumers can distinguish them from provider-produced forecasts.
    op.execute("UPDATE forecast_cache SET provider = 'legacy' WHERE provider IS NULL")


def downgrade() -> None:
    op.drop_column("forecast_cache", "generated_at")
    op.drop_column("forecast_cache", "data_quality_json")
    op.drop_column("forecast_cache", "fallback_reason")
    op.drop_column("forecast_cache", "interval_type")
    op.drop_column("forecast_cache", "horizon_days")
    op.drop_column("forecast_cache", "context_days")
    op.drop_column("forecast_cache", "data_end")
    op.drop_column("forecast_cache", "data_start")
    op.drop_column("forecast_cache", "provider")