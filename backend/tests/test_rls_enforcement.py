"""Prove that PostgreSQL Row-Level Security isolates tenant rows.

This test runs the full Alembic migration chain (including RLS policies and
``nazmos_app`` role creation) against a disposable schema in the test database,
then verifies that:

1. The table owner bypasses RLS and sees all rows.
2. When the application issues ``SET ROLE nazmos_app`` and sets
   ``app.current_tenant_id`` to a single tenant, only that tenant's rows are
   visible.

This is the production enforcement path: the app connects as the migration
owner but assumes the restricted role so RLS policies are active.
"""
import os
import subprocess
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.database import connection as connection_mod


TEST_DATABASE_URL = "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test"
APP_ROLE = "nazmos_app"


def _run_alembic_upgrade() -> None:
    """Run ``alembic upgrade head`` in the backend directory."""
    import sys

    backend_dir = os.path.join(os.path.dirname(__file__), "..")
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


@pytest.fixture(scope="module")
def rls_engine():
    """Create a migrated test schema with RLS policies and app role."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    async def setup():
        async with engine.begin() as conn:
            # Drop everything in public to get a clean slate, then recreate it.
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO nazmos"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
        await engine.dispose()

    import asyncio
    asyncio.run(setup())
    _run_alembic_upgrade()

    # Re-create engine after schema recreation.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield engine

    async def teardown():
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(teardown())


@pytest_asyncio.fixture(scope="function")
async def rls_session(rls_engine) -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = async_sessionmaker(rls_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
def app_role_enabled(monkeypatch):
    """Patch connection settings so sessions will SET ROLE nazmos_app."""
    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_APP_ROLE", APP_ROLE)
    monkeypatch.setattr(connection_mod, "settings", settings)


async def _seed_two_businesses(session: AsyncSession) -> tuple[str, str, str, str]:
    """Create two businesses, each with one item. Returns (bus_a, bus_b, item_a, item_b)."""
    bus_a = str(uuid.uuid4())
    bus_b = str(uuid.uuid4())
    item_a = str(uuid.uuid4())
    item_b = str(uuid.uuid4())

    await session.execute(
        text("""
            INSERT INTO users (id, email, password_hash, full_name, role, is_active)
            VALUES (:id, :email, 'hash', 'Owner', 'owner', true)
        """),
        {"id": str(uuid.uuid4()), "email": f"rls_owner_{uuid.uuid4().hex[:8]}@example.com"},
    )

    await session.execute(
        text("INSERT INTO businesses (id, name, type, currency) VALUES (:id, 'A', 'retail', 'SAR')"),
        {"id": bus_a},
    )
    await session.execute(
        text("INSERT INTO businesses (id, name, type, currency) VALUES (:id, 'B', 'retail', 'SAR')"),
        {"id": bus_b},
    )

    await session.execute(
        text("""
            INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active)
            VALUES (:id, :business_id, 'Item A', 'A-001', 'piece', 10, 20, true)
        """),
        {"id": item_a, "business_id": bus_a},
    )
    await session.execute(
        text("""
            INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active)
            VALUES (:id, :business_id, 'Item B', 'B-001', 'piece', 10, 20, true)
        """),
        {"id": item_b, "business_id": bus_b},
    )
    await session.commit()
    return bus_a, bus_b, item_a, item_b


@pytest.mark.asyncio
async def test_owner_bypasses_rls(rls_session: AsyncSession):
    """Sanity check: owner connection sees rows from both tenants."""
    bus_a, bus_b, item_a, item_b = await _seed_two_businesses(rls_session)

    result = await rls_session.execute(text("SELECT id, business_id FROM items ORDER BY name"))
    rows = result.fetchall()
    ids = {str(r.id) for r in rows}
    assert {item_a, item_b}.issubset(ids), "Owner should see both items"


@pytest.mark.asyncio
async def test_app_role_isolates_tenant_rows(
    rls_engine, app_role_enabled, monkeypatch
):
    """With SET ROLE nazmos_app + tenant context, only tenant A rows are visible."""
    SessionLocal = async_sessionmaker(rls_engine, class_=AsyncSession, expire_on_commit=False)

    # Seed as owner.
    async with SessionLocal() as owner_session:
        bus_a, bus_b, item_a, item_b = await _seed_two_businesses(owner_session)

    # Now open a session that will assume the restricted role and tenant A.
    async with SessionLocal() as restricted_session:
        # The _set_rls_context helper reads the context var; set it for bus_a.
        from app.database.connection import set_rls_tenant_id
        token = set_rls_tenant_id(bus_a)
        try:
            await connection_mod._set_rls_context(restricted_session)
            result = await restricted_session.execute(
                text("SELECT id, business_id FROM items ORDER BY name")
            )
            rows = result.fetchall()
            ids = {str(r.id) for r in rows}
            assert item_a in ids, "Tenant A should see its own item"
            assert item_b not in ids, "Tenant A must not see tenant B item"
            assert len(ids) == 1, f"Expected exactly one row, got {ids}"
        finally:
            connection_mod._rls_tenant_id.reset(token)
