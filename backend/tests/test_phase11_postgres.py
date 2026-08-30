"""Phase 11 — non-destructive PostgreSQL concurrency matrix (§Part 2).

Extends Phase 9's concurrency proof. Uses isolated UUIDs and idempotent create_all; never
drops the shared schema. Skips automatically when Postgres is unavailable (same convention
as the rest of the Postgres-gated suite); runs in CI.
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
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
        await conn.run_sync(Base.metadata.create_all)  # idempotent (checkfirst)
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


async def _item_inventory(db: AsyncSession, bid: str, stock: float) -> tuple[str, str, str]:
    item_id = str(uuid4())
    # Branches are separate businesses (inventory is keyed by business_id+item_id).
    src = await _seed(db, "SRC")
    dst = await _seed(db, "DST")
    await db.execute(text("INSERT INTO items (id, business_id, name, cost_price, sell_price) VALUES (:i, :b, 'Milk', 1.0, 2.0)"),
                     {"i": item_id, "b": bid})
    await db.execute(text("INSERT INTO inventory (id, business_id, item_id, current_stock) VALUES (:s, :src, :i, :stock), (:d, :dst, :i, 0)"),
                     {"s": str(uuid4()), "d": str(uuid4()), "src": src, "dst": dst, "i": item_id, "stock": stock})
    await db.commit()
    return item_id, src, dst


async def test_concurrent_transfers_stock_never_negative(db):
    """§C: two overlapping transfers of the same item — stock ≥ 0, exactly one succeeds."""
    from app.services.agent_action_executor import _execute_transfer

    bid = await _seed(db)
    item_id, src, dst = await _item_inventory(db, bid, 10.0)

    async def transfer(qty: int):
        async with async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)() as s:
            result = await _execute_transfer(s, bid, {
                "item_id": item_id, "from_business_id": src, "to_business_id": dst,
                "recommended_transfer_qty": qty,
            })
            await s.commit()
            return result

    r1, r2 = await asyncio.gather(transfer(8), transfer(8))
    assert sum(1 for r in (r1, r2) if r.get("executed")) == 1

    stock = await db.execute(text("SELECT current_stock FROM inventory WHERE business_id = :s AND item_id = :i"),
                             {"s": src, "i": item_id})
    assert float(stock.scalar()) >= 0  # invariant


async def test_duplicate_approval_is_idempotent(db):
    """§B: two concurrent approvals → one terminal transition, second is a no-op."""
    from app.services.agent_action_executor import approve_agent_action

    bid = await _seed(db)
    aid = str(uuid4())
    await db.execute(text("""
        INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority,
                                   title, summary, payload, autonomy_dial_at_creation, was_auto_executed, created_at, updated_at)
        VALUES (:id, :b, 'pricing_decrease', 'pending_approval', 0.9, 3, 'x', 'y', '{}', 50, false, now(), now())
    """), {"id": aid, "b": bid})
    await db.commit()

    async def approve():
        async with async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)() as s:
            return await approve_agent_action(s, aid, note="approve")

    r1, r2 = await asyncio.gather(approve(), approve())
    assert sorted([r1["ok"], r2["ok"]]) == [False, True]  # exactly one wins


async def test_tenant_isolation_under_concurrency(db):
    """§F: business A and B run actions concurrently; A never sees B's learned outcomes."""
    from app.services.agent_action_executor import _record_terminal_outcome
    from app.services.outcome_learning import list_learned_outcomes

    bid_a = await _seed(db, "A")
    bid_b = await _seed(db, "B")

    async def make_action(bid: str) -> str:
        aid = str(uuid4())
        async with async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)() as s:
            await s.execute(text("""
                INSERT INTO agent_actions (id, business_id, action_type, status, confidence, priority,
                                           title, summary, payload, autonomy_dial_at_creation, was_auto_executed,
                                           outcome_json, created_at, updated_at)
                VALUES (:id, :b, 'discount', 'approved', 0.9, 3, 'x', 'y', '{}', 50, false, :out, now(), now())
            """), {"id": aid, "b": bid, "out": json.dumps({"executed": True})})
            await s.commit()
        return aid

    aid_a = await make_action(bid_a)
    aid_b = await make_action(bid_b)

    async def record(bid: str, aid: str):
        async with async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)() as s:
            return await _record_terminal_outcome(s, bid, aid)

    await asyncio.gather(
        record(bid_a, aid_a),
        record(bid_b, aid_b),
    )

    a_out = await list_learned_outcomes(db, bid_a)
    b_out = await list_learned_outcomes(db, bid_b)
    assert len(a_out) == 1 and len(b_out) == 1
    # A's learned outcome is only for A's action.
    assert a_out[0]["action_type"] == "discount"
