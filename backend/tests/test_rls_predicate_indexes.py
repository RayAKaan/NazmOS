"""Tests for RLS predicate indexes (Phase 1.7).

Every table guarded by a ``business_id = app.current_tenant_id()`` RLS policy
needs an index with ``business_id`` as the leading column.  This list mirrors
``TENANT_TABLES`` in alembic/versions/a25a714a2de8_add_tenant_rls_policies.py
so a future table addition without an index fails loudly here.

A leading-column ``business_id`` unique constraint also satisfies the RLS
predicate, so both indexes and unique constraints are inspected.
"""
import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.database.models import Base

TENANT_TABLES = [
    "agent_actions",
    "analytics_cache",
    "audit_log",
    "autonomy_policies",
    "billing_events",
    "categories",
    "chat_sessions",
    "daily_summaries",
    "decision_log",
    "enabled_modules",
    "executed_actions",
    "forecast_cache",
    "inventory",
    "items",
    "money_audit_actions",
    "money_audits",
    "notification_preferences",
    "notifications",
    "pharmacy_lots",
    "pos_connections",
    "pricing_recommendations",
    "pricing_rules",
    "purchase_orders",
    "recipes",
    "recovery_match_settings",
    "reports",
    "subscriptions",
    "transactions",
    "uploaded_files",
]


@pytest.fixture
async def business_indexed_tables():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _collect(sync_conn) -> dict[str, bool]:
            inspector = inspect(sync_conn)
            result = {}
            for table in TENANT_TABLES:
                indexed = False
                for idx in inspector.get_indexes(table):
                    cols = idx.get("column_names") or []
                    if cols and cols[0] == "business_id":
                        indexed = True
                        break
                if not indexed:
                    for uc in inspector.get_unique_constraints(table):
                        cols = uc.get("column_names") or []
                        if cols and cols[0] == "business_id":
                            indexed = True
                            break
                result[table] = indexed
            return result

        yield await conn.run_sync(_collect)
    await engine.dispose()


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_rls_table_has_business_index(business_indexed_tables, table):
    assert business_indexed_tables[table], (
        f"{table} lacks an index/constraint leading with business_id for its RLS predicate"
    )
