"""Celery / background workers must carry explicit RLS tenant context.

FastAPI requests get ``app.current_tenant_id`` from ``TenantContextMiddleware``.
Celery workers have no HTTP request, so every background session previously
ran WITHOUT a tenant context: in production (restricted ``nazmos_app`` role)
that means zero rows visible — a silent cross-isolation hole; in development
(SQLite, no RLS) it means fully unscoped queries.

The fix under test:
- ``get_sync_session(tenant_id=...)`` scopes a whole task body (including any
  sibling fresh async engine the ETL opens) to one tenant.
- ``sync_rls_tenant_context(...)`` covers ``AsyncSessionLocal`` sessions opened
  by audit/learning/memory/compliance tasks.
- The sync engine begin-listener mirrors the async one, so ``SET LOCAL`` is
  re-issued on every transaction begin.

Verified against a real Postgres test DB with the Alembic chain applied:
1. A scoped sync session sees only its own tenant's rows.
2. A scoped sync session cannot read or write another tenant's rows.
3. A session with NO tenant context fails closed (sees zero tenant rows).
4. ``sync_rls_tenant_context`` scopes async sessions the same way.
5. Owned (supervisor) connections still enumerate all tenants for scheduler jobs.
6. A non-UUID tenant id is rejected before it can reach ``SET LOCAL``.
"""
import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.database import connection as connection_mod
from app.database.connection import (
    AsyncSessionLocal,
    get_sync_session,
    sync_rls_tenant_context,
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test",
)
APP_ROLE = "nazmos_app"


@pytest.fixture(scope="module")
def migrated_db():
    """Ensure the test DB is migrated to head.

    Unlike ``tests/test_rls_enforcement.py`` this does NOT drop/recreate the
    schema, so it does not disturb other DB-backed suites sharing the test DB.
    """
    if connection_mod._is_sqlite:
        pytest.skip("RLS tenant context tests require PostgreSQL")
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    env = os.environ.copy()
    env["DATABASE_URL"] = TEST_DATABASE_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic upgrade failed:\n{result.stdout}\n{result.stderr}")
    yield


def _enable_app_role(monkeypatch):
    """Make the app assume the restricted role from this point on."""
    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_APP_ROLE", APP_ROLE)
    monkeypatch.setattr(connection_mod, "settings", settings)


def _seed_two_businesses(owner_session):
    """Create two businesses, each with one item. Returns (bus_a, bus_b)."""
    bus_a = str(uuid.uuid4())
    bus_b = str(uuid.uuid4())
    item_a = str(uuid.uuid4())
    item_a_secret = str(uuid.uuid4())
    item_b = str(uuid.uuid4())

    owner_session.execute(
        text("""
            INSERT INTO users (id, email, password_hash, full_name, role, is_active)
            VALUES (:id, :email, 'hash', 'Owner', 'owner', true)
        """),
        {"id": str(uuid.uuid4()), "email": f"celery_rls_{uuid.uuid4().hex[:8]}@example.com"},
    )
    for b in (bus_a, bus_b):
        owner_session.execute(
            text("INSERT INTO businesses (id, name, type, currency) VALUES (:id, :n, 'retail', 'SAR')"),
            {"id": b, "n": f"Biz {b[:8]}"},
        )
    owner_session.execute(
        text(
            "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
            "VALUES (:id, :b, :name, :sku, 'piece', 10, 20, true)"
        ),
        {"id": item_a, "b": bus_a, "name": "Item A", "sku": f"SKU-A-{uuid.uuid4().hex[:6]}"},
    )
    owner_session.execute(
        text(
            "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
            "VALUES (:id, :b, :name, :sku, 'piece', 1, 5, true)"
        ),
        {"id": item_a_secret, "b": bus_a, "name": "Item Secret",
         "sku": f"SKU-S-{uuid.uuid4().hex[:6]}"},
    )
    owner_session.execute(
        text(
            "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
            "VALUES (:id, :b, :name, :sku, 'piece', 10, 20, true)"
        ),
        {"id": item_b, "b": bus_b, "name": "Item B", "sku": f"SKU-B-{uuid.uuid4().hex[:6]}"},
    )
    owner_session.commit()
    return {
        "bus_a": bus_a,
        "bus_b": bus_b,
        "item_a": item_a,
        "item_a_secret": item_a_secret,
        "item_b": item_b,
    }


def _visible_items(session) -> set:
    result = session.execute(text("SELECT id, business_id FROM items"))
    return {(str(r.id) if r.id else None, str(r.business_id) if r.business_id else None)
            for r in result.fetchall()}


@pytest.mark.skipif(connection_mod._is_sqlite, reason="Needs PostgreSQL RLS")
class TestSyncSessionTenantScope:
    """The Celery worker sync-session path applies RLS per tenant."""

    def test_scoped_sync_session_sees_only_own_tenant(self, migrated_db, monkeypatch):
        with get_sync_session() as owner:
            s = _seed_two_businesses(owner)
        _enable_app_role(monkeypatch)

        with get_sync_session(tenant_id=s["bus_a"]) as scoped:
            rows = _visible_items(scoped)
        assert (s["item_a"], s["bus_a"]) in rows
        assert (s["item_a_secret"], s["bus_a"]) in rows
        assert (s["item_b"], s["bus_b"]) not in rows
        assert len(rows) == 2, f"Exactly tenant A's rows expected, got {rows}"

    def test_scoped_sync_session_cannot_write_other_tenant(self, migrated_db, monkeypatch):
        with get_sync_session() as owner:
            s = _seed_two_businesses(owner)
        _enable_app_role(monkeypatch)

        with get_sync_session(tenant_id=s["bus_a"]) as scoped:
            with pytest.raises(Exception):
                scoped.execute(
                    text(
                        "INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active) "
                        "VALUES (:id, :b, 'poison', 'SKU-P', 'piece', 1, 2, true)"
                    ),
                    {"id": str(uuid.uuid4()), "b": s["bus_b"]},
                )
            scoped.rollback()

    def test_no_tenant_fails_closed(self, migrated_db, monkeypatch):
        """Restricted role + no tenant = sees zero tenant rows (never everything)."""
        with get_sync_session() as owner:
            s = _seed_two_businesses(owner)
        _enable_app_role(monkeypatch)

        with get_sync_session() as unscoped:
            rows = _visible_items(unscoped)
        assert rows == set(), f"Background worker without tenant must fail closed, got {rows}"

    def test_supervisor_connection_enumerates_all_tenants(self, migrated_db):
        """Without the restricted role (production scheduler/owner path) all rows are visible."""
        with get_sync_session() as owner:
            s = _seed_two_businesses(owner)
            rows = _visible_items(owner)
        assert (s["item_a"], s["bus_a"]) in rows
        assert (s["item_b"], s["bus_b"]) in rows


@pytest.mark.skipif(connection_mod._is_sqlite, reason="Needs PostgreSQL RLS")
class TestSyncTenantContextAsyncCoverage:
    """`sync_rls_tenant_context` also scopes AsyncSessionLocal sessions."""

    @pytest.mark.asyncio
    async def test_async_session_in_context_sees_only_own_tenant(self, migrated_db, monkeypatch):
        with get_sync_session() as owner:
            s = _seed_two_businesses(owner)
        _enable_app_role(monkeypatch)

        with sync_rls_tenant_context(s["bus_a"]):
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("SELECT id, business_id FROM items"))
                rows = {(str(r.id), str(r.business_id)) for r in result.fetchall()}

        assert (s["item_a"], s["bus_a"]) in rows
        assert (s["item_a_secret"], s["bus_a"]) in rows
        assert (s["item_b"], s["bus_b"]) not in rows

    @pytest.mark.asyncio
    async def test_nested_context_restores_previous_tenant(self, migrated_db, monkeypatch):
        with get_sync_session() as owner:
            s = _seed_two_businesses(owner)

        outer = inner = after = None
        with sync_rls_tenant_context(s["bus_a"]):
            outer = connection_mod.get_rls_tenant_id()
            with sync_rls_tenant_context(s["bus_b"]):
                inner = connection_mod.get_rls_tenant_id()
        after = connection_mod.get_rls_tenant_id()
        assert outer == s["bus_a"]
        assert inner == s["bus_b"]
        assert after is None, "context must be fully restored after exiting"


@pytest.mark.skipif(connection_mod._is_sqlite, reason="Needs PostgreSQL RLS")
class TestInvalidTenantContext:
    def test_non_uuid_tenant_rejected(self, migrated_db):
        for payload in (
            "business-A; DROP TABLE items --",
            "a'; DELETE FROM items; --",
            "not-a-uuid",
        ):
            with pytest.raises(ValueError):
                with sync_rls_tenant_context(payload):
                    pass