"""index rls predicate columns

Revision ID: c4d6e8f0a2b1
Revises: 8b3f5c2a1d94
Create Date: 2026-08-06

Every table protected by a ``business_id = app.current_tenant_id()`` RLS
policy needs an index whose leading column is ``business_id`` so the policy
predicate can be satisfied without a sequential scan.  Two tenant tables were
missing one:

- ``billing_events`` had no business_id index at all.
- ``notification_preferences`` had only a user_id-leading unique constraint,
  which cannot serve the RLS predicate.

Tables covered by an existing business_id-leading index or constraint (e.g.
``uq_analytics_cache_key``) are intentionally not duplicated here.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4d6e8f0a2b1"
down_revision: Union[str, None] = "8b3f5c2a1d94"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_billing_events_business",
        "billing_events",
        ["business_id"],
    )
    op.create_index(
        "idx_notification_preferences_business",
        "notification_preferences",
        ["business_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_notification_preferences_business", table_name="notification_preferences")
    op.drop_index("idx_billing_events_business", table_name="billing_events")
