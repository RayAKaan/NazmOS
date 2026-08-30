"""Phase 13 — PostgreSQL concurrency matrix (§Part 22).

Postgres-gated, non-destructive (isolated UUIDs + idempotent create_all; never DROP SCHEMA).
Extends Phase 11/12 concurrency coverage with failure-rollback and reconciliation races.

Skips automatically when Postgres is unavailable; runs in CI.
"""
from __future__ import annotations

import asyncio
import json
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


def _pg() -> bool:
    try:
        with socket.create_connection(("localhost", 5432), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _pg(), reason="Postgres test DB unavailable")


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
        await conn.run_sync(Base.metadata.create_all)
    S = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with S() as session:
        yield session
    await engine.dispose()


async def _seed(db, name="T") -> str:
    bid = str(uuid4())
    await db.execute(text("INSERT INTO businesses (id, name, type, is_active) VALUES (:id, :n, 'retail', true)"),
                     {"id": bid, "n": name})
    await db.commit()
    return bid


async def test_concurrent_transfers_stock_non_negative(db):
    from app.services.agent_action_executor import _execute_transfer

    bid = await _seed(db)
    item = str(uuid4())
    # Branches are separate businesses (inventory is keyed by business_id+item_id).
    src = await _seed(db, "S")
    dst = await _seed(db, "D")
    await db.execute(text("INSERT INTO items (id, business_id, name, cost_price, sell_price) VALUES (:i,:b,'M',1,2)"),
                     {"i": item, "b": bid})
    await db.execute(text("INSERT INTO inventory (id, business_id, item_id, current_stock) VALUES (:s,:src,:i,10),(:d,:dst,:i,0)"),
                     {"s": str(uuid4()), "d": str(uuid4()), "src": src, "dst": dst, "i": item})
    await db.commit()

    async def xfer(q):
        async with async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)() as s:
            result = await _execute_transfer(s, bid, {"item_id": item, "from_business_id": src,
                                                      "to_business_id": dst, "recommended_transfer_qty": q})
            await s.commit()
            return result

    r1, r2 = await asyncio.gather(xfer(8), xfer(8))
    assert sum(1 for r in (r1, r2) if r.get("executed")) == 1
    stock = await db.execute(text("SELECT current_stock FROM inventory WHERE business_id = :s AND item_id = :i"),
                             {"s": src, "i": item})
    assert float(stock.scalar()) >= 0


async def test_duplicate_approval_idempotent(db):
    from app.services.agent_action_executor import approve_agent_action

    bid = await _seed(db)
    aid = str(uuid4())
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority, title, summary,
                                   payload, autonomy_dial_at_creation, was_auto_executed, created_at, updated_at)
        VALUES (:id,:b,'pricing_decrease','pending_approval',0.9,3,'x','y','{}',50,false,now(),now())
    """), {"id": aid, "b": bid})
    await db.commit()

    async def ap():
        async with async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)() as s:
            return await approve_agent_action(s, aid, note="x")

    a, b = await asyncio.gather(ap(), ap())
    assert sorted([a["ok"], b["ok"]]) == [False, True]


async def test_concurrent_reconciliation_no_duplicate_learning(db):
    from app.services.learning_reconciliation import reconcile_all

    bid = await _seed(db)
    aid = str(uuid4())
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority, title, summary,
                                   payload, autonomy_dial_at_creation, was_auto_executed, outcome_json, created_at, updated_at)
        VALUES (:id,:b,'discount','approved',0.9,3,'x','y','{}',50,false,:out,now(),now())
    """), {"id": aid, "b": bid, "out": json.dumps({"executed": True})})
    await db.commit()

    async def rec():
        async with async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)() as s:
            return await reconcile_all(s, bid)

    await asyncio.gather(rec(), rec())

    lo = await db.execute(text("SELECT COUNT(*) FROM learned_outcomes WHERE agent_action_id=:a"), {"a": aid})
    of = await db.execute(text("SELECT COUNT(*) FROM outcome_feedback WHERE agent_action_id=:a"), {"a": aid})
    assert lo.scalar() == 1
    assert of.scalar() == 1
