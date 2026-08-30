"""Phase 9 — PostgreSQL concurrency + transaction integration tests (§2–5, §30).

These tests exercise real PostgreSQL semantics (FOR UPDATE row locking, true concurrent
transactions, tenant isolation under concurrency) that SQLite cannot prove. They skip
automatically when the Postgres test database is unavailable (same convention as
`tests/test_rls_enforcement.py`).

Run in CI where `nazmos:nazmos_dev@localhost:5432/nazmos_test` exists.
"""
from __future__ import annotations

import asyncio
import os
import socket
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test",
)


def _postgres_available() -> bool:
    try:
        with socket.create_connection(("localhost", 5432), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="Postgres test DB unavailable")


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    # NOTE: do NOT drop/recreate the public schema — this test runs inside the shared
    # `pytest -q` CI invocation against the same nazmos_test database as every other
    # Postgres test. create_all is idempotent (checkfirst) and all seeded rows use unique
    # UUIDs, so tests neither clobber nor collide with the rest of the suite.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession, name: str = "Test") -> str:
    bid = str(uuid4())
    await db.execute(text("INSERT INTO businesses (id, name, type, is_active) VALUES (:id, :n, 'retail', true)"),
                     {"id": bid, "n": name})
    await db.commit()
    return bid


async def test_concurrent_transfers_cannot_overdraw_inventory(db):
    """§2/§4: two concurrent transfers of the same item cannot drive stock negative —
    the FOR UPDATE row lock serializes them and the second sees insufficient stock."""
    bid = await _seed(db)
    item_id = str(uuid4())
    # Branches are separate businesses (inventory is keyed by business_id+item_id).
    branch_a = await _seed(db, "Branch A")
    branch_b = await _seed(db, "Branch B")
    await db.execute(text("""
        INSERT INTO items (id, business_id, name, cost_price, sell_price) VALUES (:i, :b, 'Milk', 1.0, 2.0)
    """), {"i": item_id, "b": bid})
    await db.execute(text("""
        INSERT INTO inventory (id, business_id, item_id, current_stock) VALUES
        (:ia, :ba, :i, 10), (:ib, :bb, :i, 0)
    """), {"ia": str(uuid4()), "ib": str(uuid4()), "ba": branch_a, "bb": branch_b, "i": item_id})
    await db.commit()

    from app.services.agent_action_executor import _execute_transfer

    # Two transfers of 8 units each from branch_a (only 10 available) — one must fail.
    async def transfer(qty: int):
        async with async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)() as s:
            result = await _execute_transfer(s, bid, {
                "item_id": item_id, "from_business_id": branch_a, "to_business_id": branch_b,
                "recommended_transfer_qty": qty,
            })
            await s.commit()
            return result

    r1, r2 = await asyncio.gather(transfer(8), transfer(8))
    executed = sum(1 for r in (r1, r2) if r.get("executed"))
    assert executed == 1  # exactly one transfer succeeds

    stock = await db.execute(text("SELECT current_stock FROM inventory WHERE business_id = :ba AND item_id = :i"),
                             {"ba": branch_a, "i": item_id})
    assert float(stock.scalar()) >= 0  # invariant: stock never negative


async def test_same_action_duplicate_execution_prevented(db):
    """§2/§5: the approval path is idempotent — a second approve of an already-approved
    action does nothing."""
    from app.services.agent_action_executor import approve_agent_action, reject_agent_action

    bid = await _seed(db)
    aid = str(uuid4())
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority,
                                   title, summary, payload, autonomy_dial_at_creation, was_auto_executed,
                                   created_at, updated_at)
        VALUES (:id, :b, 'pricing_decrease', 'pending_approval', 0.9, 3, 'x', 'y', '{}', 50, false, now(), now())
    """), {"id": aid, "b": bid})
    await db.commit()

    r1 = await approve_agent_action(db, aid, note="first")
    r2 = await approve_agent_action(db, aid, note="second")  # already approved → no-op
    assert r1["ok"] is True
    assert r2["ok"] is False  # idempotent: second approval rejected
