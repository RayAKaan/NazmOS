"""Metamorphic safety net for the DuckDB analytical boundary (Phase 1).

The DuckDB engine is the analytical execution layer for the inventory
money-critical surface. These tests pin the invariants that the replacement
must never silently break, mirroring the same class of guarantees the golden
CSV regression and adversarial matrix enforce for the canonical financial
chain:

  - row-order invariance: KPI output is independent of transaction row order.
  - tenant isolation: one business can never observe another's rows through
    the engine; provenance carries the tenant id.
  - date-coverage sensitivity: 6 observed days must never be treated as 30
    ("6-as-30" regression), and 7/14-day trend windows stay exact.
  - identity: item id / name / sku survive the engine round-trip.
  - duplicates: duplicated transaction rows sum exactly (no double-counting
    beyond the rows that actually exist).
  - missing/empty: no rows, no inventory -> empty feed; raw NULLs -> zeros.
  - cost vs sell basis: explicit ValueBasis selects the price; cost value and
    sell value differ by construction.
  - money discipline: even after DuckDB's DOUBLE results, every monetary value
    is Decimal at 0.01 with no float noise.
  - fail-closed: a broken load raises ScopedEngineError and never leaves a
    live engine handle behind.
"""
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.analytics import inventory_feed
from app.analytics.contracts import ValueBasis
from app.analytics.metrics import daily_velocity, dead_stock_total, stock_value
from app.database.models import (
    Base,
    Business,
    Category,
    Inventory,
    Item,
    Transaction,
)

NOW = datetime(2026, 9, 7, 10, 0, 0)  # deterministic anchor for every test

d30 = NOW - timedelta(days=30)
d14 = NOW - timedelta(days=14)
d7 = NOW - timedelta(days=7)


def _tx(business_id, item_id, qty, at):
    return Transaction(
        id=uuid.uuid4(),
        business_id=business_id,
        item_id=item_id,
        quantity=qty,
        unit_price=1.0,
        cost_price=0.5,
        total_amount=float(qty),
        profit=float(qty) * 0.5,
        transaction_at=at,
    )


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


async def _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,), names=("Item",)):
    business = Business(id=uuid.uuid4(), name="Metamorphic", type="baqala")
    db.add(business)
    await db.flush()
    items = [
        Item(
            id=uuid.uuid4(),
            business_id=business.id,
            name=names[i],
            sku=f"SKU-{i}",
            cost_price=costs[i],
            sell_price=sells[i],
        )
        for i in range(len(names))
    ]
    db.add_all(items)
    await db.flush()
    for i, it in enumerate(items):
        db.add(Inventory(
            id=uuid.uuid4(),
            business_id=business.id,
            item_id=it.id,
            current_stock=stock[i],
        ))
    await db.commit()
    return business.id, [str(it.id) for it in items]


async def test_row_order_invariance(db):
    """Same facts, reversed transaction rows -> identical KPIs and provenance."""
    bid, iids = await _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,))
    forward = [
        _tx(bid, iids[0], 3, d30 + timedelta(days=1)),
        _tx(bid, iids[0], 5, d30 + timedelta(days=2)),
        _tx(bid, iids[0], 2, NOW - timedelta(days=1)),
    ]
    db.add_all(forward)
    await db.commit()
    feed_a = await inventory_feed(db, bid, anchor=NOW)

    # Wipe and re-seed in a different order.
    for row in (await db.execute(
        select(Transaction).where(Transaction.business_id == bid)
    )).scalars():
        await db.delete(row)
    await db.commit()
    reversed_rows = [_tx(bid, iids[0], 2, NOW - timedelta(days=1)),
                     _tx(bid, iids[0], 5, d30 + timedelta(days=2)),
                     _tx(bid, iids[0], 3, d30 + timedelta(days=1))]
    db.add_all(reversed_rows)
    await db.commit()
    feed_b = await inventory_feed(db, bid, anchor=NOW)

    assert feed_a.provenance == feed_b.provenance
    ka, kb = feed_a.by_item_id(iids[0]), feed_b.by_item_id(iids[0])
    assert daily_velocity(ka) == daily_velocity(kb)
    assert ka.qty_30d == kb.qty_30d == 10.0
    assert ka.coverage_days_30d == kb.coverage_days_30d == 3
    assert ka.last_sold_at == kb.last_sold_at


async def test_tenant_isolation(db):
    """Two businesses, identical SKUs: one business can never see the other's qty."""
    bid_a, ids_a = await _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,), names=("Milk",))
    bid_b, ids_b = await _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,), names=("Milk",))

    db.add(_tx(bid_a, ids_a[0], 50, d30 + timedelta(days=1)))
    db.add(_tx(bid_b, ids_b[0], 2, d30 + timedelta(days=1)))
    await db.commit()

    feed_a = await inventory_feed(db, bid_a, anchor=NOW)
    feed_b = await inventory_feed(db, bid_b, anchor=NOW)

    assert feed_a.provenance.business_id == str(bid_a)
    assert feed_a.by_item_id(ids_b[0]) is None, "B's item must not appear in A's feed"
    assert feed_a.by_item_id(ids_a[0]).qty_30d == 50.0
    assert feed_b.by_item_id(ids_b[0]).qty_30d == 2.0
    assert feed_b.by_item_id(ids_a[0]) is None
    assert daily_velocity(feed_a.by_item_id(ids_a[0])) == 50.0
    assert daily_velocity(feed_b.by_item_id(ids_b[0])) == 2.0


async def test_coverage_sensitive_velocity_never_treats_6_days_as_30(db):
    """'6-as-30' regression: 12 units over 6 observed days -> 2.0/day, not 0.4."""
    bid, iids = await _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,))
    for day in range(6):
        db.add(_tx(bid, iids[0], 2, d30 + timedelta(days=day)))
    await db.commit()

    feed = await inventory_feed(db, bid, anchor=NOW)
    fact = feed.by_item_id(iids[0])
    assert fact.qty_30d == 12.0
    assert fact.coverage_days_30d == 6
    assert daily_velocity(fact) == 2.0  # 12/6, NOT 12/30
    assert feed.provenance.observed_days == 6


async def test_trend_windows_stay_exact(db):
    """7d and previous-7d windows are computed over exact boundaries."""
    bid, iids = await _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,))
    db.add(_tx(bid, iids[0], 4, NOW - timedelta(days=1)))   # recent 7d
    db.add(_tx(bid, iids[0], 2, NOW - timedelta(days=9)))   # prev 7d (7-14d ago)
    db.add(_tx(bid, iids[0], 9, NOW - timedelta(days=20)))  # outside both -> dead? no, has qty_30d
    await db.commit()

    feed = await inventory_feed(db, bid, anchor=NOW)
    fact = feed.by_item_id(iids[0])
    assert fact.qty_7d == 4.0
    assert fact.qty_prev7d == 2.0
    assert fact.qty_30d == 15.0
    from app.analytics.metrics import trend_7d
    assert trend_7d(fact.qty_7d, fact.qty_prev7d) == "up"
    assert not fact.dead_by_scan


async def test_identity_and_duplicate_rows(db):
    """id/name/sku round-trip; duplicated sale rows sum exactly."""
    bid, iids = await _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,), names=("Bread",))
    db.add(_tx(bid, iids[0], 3, d30 + timedelta(days=1)))
    db.add(_tx(bid, iids[0], 3, d30 + timedelta(days=1)))  # duplicate row, distinct id
    await db.commit()

    feed = await inventory_feed(db, bid, anchor=NOW)
    fact = feed.by_item_id(iids[0])
    assert fact.name == "Bread"
    assert fact.sku == "SKU-0"
    assert fact.qty_30d == 6.0, "duplicate rows must sum, not overwrite"
    assert fact.coverage_days_30d == 1


async def test_empty_and_partial_coverage(db):
    """Empty business -> empty feed; items with no sales are dead, not NaN."""
    bid, iids = await _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,))
    feed = await inventory_feed(db, bid, anchor=NOW)
    fact = feed.by_item_id(iids[0])
    assert feed.provenance.observed_days == 0
    assert fact.qty_30d == 0.0
    assert fact.coverage_days_30d == 0
    assert daily_velocity(fact) == 0
    assert fact.qty_7d == 0.0 and fact.qty_prev7d == 0.0
    assert fact.dead_by_scan and fact.current_stock > 0
    assert stock_value(fact.current_stock, fact.cost_price, ValueBasis.COST) == 40.00
    assert float(dead_stock_total(feed, ValueBasis.COST)) == 40.0

    empty_bid = str(uuid.uuid4())
    feed_empty = await inventory_feed(db, empty_bid, anchor=NOW)
    assert feed_empty.facts == []
    assert float(dead_stock_total(feed_empty, ValueBasis.COST)) == 0.0


async def test_cost_vs_sell_basis(db):
    """Same stock, explicit basis: cost value and sell value differ by design."""
    bid, iids = await _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,))
    feed = await inventory_feed(db, bid, anchor=NOW)
    fact = feed.by_item_id(iids[0])
    assert stock_value(fact.current_stock, fact.cost_price, ValueBasis.COST) == 40.00
    assert stock_value(fact.current_stock, fact.sell_price, ValueBasis.SELL) == 60.00
    assert 40.00 != 60.00


async def test_money_discipline_no_float_noise(db):
    """Rounding / Decimal discipline holds after DuckDB DOUBLE arithmetic."""
    bid, iids = await _seed_business(db, costs=(3.33,), sells=(9.99,), stock=(7.0,))
    for day in range(3):
        db.add(_tx(bid, iids[0], 1.0, d30 + timedelta(days=day)))
    await db.commit()
    feed = await inventory_feed(db, bid, anchor=NOW)
    fact = feed.by_item_id(iids[0])

    from decimal import Decimal

    value = stock_value(fact.current_stock, fact.cost_price, ValueBasis.COST)
    assert isinstance(value, Decimal)
    assert value == Decimal("23.31")  # 7 * 3.33 = 23.31, quantized
    assert str(value) == "23.31"
    assert float(daily_velocity(fact)) == 1.0

    dead_total = dead_stock_total(feed, ValueBasis.COST)
    assert isinstance(dead_total, Decimal) and dead_total.is_finite()


async def test_engine_fail_closed(db):
    """A broken load raises ScopedEngineError and never leaves a live handle."""
    from app.analytics.contracts import ScopedEngineError
    from app.analytics.duckdb_engine import ScopedAnalyticalEngine

    # A session with no tables -> the inventory load raises -> engine must close.
    engine_sync = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine_sync.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine_sync, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        await session.execute(Base.metadata.tables["items"].delete())
        from sqlalchemy import text as _text
        await session.execute(_text("DROP TABLE items"))
        await session.commit()
        engine = ScopedAnalyticalEngine(session, str(uuid.uuid4()), window_days=30, anchor=NOW)
        with pytest.raises(ScopedEngineError):
            await engine.__aenter__()
        assert engine._con is None, "fail-closed: no live DuckDB handle survives an error"
    await engine_sync.dispose()


async def test_anchor_boundary_uses_nazmos_session_rows(db):
    """Only rows through the caller's session are loaded (pre-authorized data)."""
    bid, iids = await _seed_business(db, costs=(2.0,), sells=(3.0,), stock=(20.0,))
    db.add(_tx(bid, iids[0], 7, d30 + timedelta(days=1)))
    await db.commit()

    feed = await inventory_feed(db, bid, anchor=NOW)
    fact = feed.by_item_id(iids[0])
    assert feed.provenance.tenant_scoped is True
    assert fact.qty_30d == 7.0
    # Rows outside the business (another bid) never enter the engine.
    other_bid, _ = await _seed_business(db, costs=(1.0,), sells=(2.0,), stock=(5.0,))
    db.add(_tx(other_bid, iids[0], 999, d30 + timedelta(days=1)))
    await db.commit()
    feed2 = await inventory_feed(db, bid, anchor=NOW)
    assert feed2.by_item_id(iids[0]).qty_30d == 7.0, "other tenant's rows leaked"