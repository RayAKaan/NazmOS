"""Phase 1 (StatsForecast): widen forecast_cache.model_version.

Longer model-version identifiers (e.g. ``statsforecast_ensemble_v1``) are
produced by the canonical StatsForecast provider. The column was ``varchar(20)``
(the legacy default was ``prophet_v1``); widening to ``varchar(50)`` matches the
other provenance columns so every provider version string persists unchanged.

Revision ID: ff09_forecast_version_widen
Revises: ff08_loc_grain_tenant_model
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "ff09_forecast_version_widen"
down_revision: Union[str, None] = "ff08_loc_grain_tenant_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "forecast_cache",
        "model_version",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "forecast_cache",
        "model_version",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=True,
    )