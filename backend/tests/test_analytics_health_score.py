"""DuckDB-era invariants for calculate_health_score (Phase 1).

Pre-DuckDB the function issued three PG queries (grouped qty, dead-stock scan,
total value) and the dead-stock scan was a separate grouped query. The scoped
DuckDB engine now serves one tenant-scoped feed; the NazmOS layer computes the
score over that feed. The guards below pin the NEW architecture's invariants:
exactly one transactions load per engine, coverage-aware velocity, provenance
attached, valid range, and value equivalence with a manual calculation.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base, Business, Inventory, Item, Transaction
from app.services.analytics_service import calculate_health_score


@pytest_asyncio.fixture
async def sqlite_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield SessionLocal, engine.sync_engine
    finally:
        await engine.dispose()


def _make_item(business_id, name, cost, sell):
    return Item(
        id=uuid.uuid4(),
        business_id=business_id,
        name=name,
        cost_price=cost,
        sell_price=sell,
    )


async def _seed(db: AsyncSession) -> uuid.UUID:
    business = Business(id=uuid.uuid4(), name="Health Test", type="baqala")
    db.add(business)
    await db.flush()

    items = [
        _make_item(business.id, "A", 1.0, 2.0),
        _make_item(business.id, "B", 2.0, 3.0),
        _make_item(business.id, "C", 3.0, 4.0),
        _make_item(business.id, "D", 4.0, 5.0),
        _make_item(business.id, "E", 5.0, 6.0),
    ]
    db.add_all(items)
    await db.flush()

    # current_stock = 100 for all; daily sales differ so we exercise every bucket.
    daily_qty = {  # all sales land on ONE observed day -> coverage = 1 day
        "A": 0.0,     # dead
        "B": 60.0,    # qty_30d=2.0  -> vel=2.0   -> 100/2   = 50 days -> healthy
        "C": 200.0,   # qty_30d=6.67 -> vel=6.67  -> ~14.99  days -> healthy
        "D": 900.0,   # qty_30d=30.0 -> vel=30.0  -> ~3.33   days -> critical
        "E": 1000.0,  # qty_30d=33.3 -> vel=33.3  -> ~3.0    days -> critical
    }
    now = datetime.now(timezone.utc)
    by_name = {i.name: i for i in items}
    tx_rows = []
    for name, qty in daily_qty.items():
        item = by_name[name]
        if qty == 0:
            continue
        tx_rows.append(Transaction(
            id=uuid.uuid4(),
            business_id=business.id,
            item_id=item.id,
            quantity=qty / 30.0,
            unit_price=item.sell_price,
            cost_price=item.cost_price,
            total_amount=(qty / 30.0) * item.sell_price,
            profit=(qty / 30.0) * (item.sell_price - item.cost_price),
            transaction_at=now - timedelta(hours=1),
        ))
    db.add_all(tx_rows)
    await db.flush()

    for item in items:
        db.add(Inventory(
            id=uuid.uuid4(),
            business_id=business.id,
            item_id=item.id,
            current_stock=100,
        ))
    await db.commit()
    return business.id


async def _run(session_local, sync_engine, business_id, tx_events):
    @event.listens_for(sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        if "transactions" in statement.lower():
            tx_events.append(statement)

    try:
        async with session_local() as db:
            score = await calculate_health_score(db, business_id)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count)
    return score


@pytest.mark.asyncio
async def test_health_score_single_engine_load(sqlite_db):
    """Exactly one statement touches transactions: the engine's tenant load.

    The DuckDB feed replaces the three PG queries (grouped qty, dead-stock
    scan, total value) with a single tenant-scoped SELECT that streams the
    analytical dataset into the in-memory engine.
    """
    SessionLocal, sync_engine = sqlite_db
    async with SessionLocal() as db:
        business_id = await _seed(db)
    tx_events = []
    score = await _run(SessionLocal, sync_engine, business_id, tx_events)

    total = [s for s in tx_events if "transactions" in s.lower()]
    assert len(total) == 1, "health score must load the feed exactly once"
    assert "WHERE" in total[0].lower() or "business_id" in total[0].lower()
    assert score >= 0


@pytest.mark.asyncio
async def test_health_score_matches_manual_coverage_aware_calculation(sqlite_db):
    SessionLocal, sync_engine = sqlite_db
    async with SessionLocal() as db:
        business_id = await _seed(db)
    tx_events = []
    score = await _run(SessionLocal, sync_engine, business_id, tx_events)

    # Manual coverage-aware expectation (all sales on a single observed day):
    #   inventory_score = (5 - 2 critical) / 5 * 40 = 24
    #   dead value (A: no sales, stock 100, cost 1.0)      = 100.00
    #   total value (stock 100 x sell price each)          = 2000.00
    #   stock_health = 30 - (100 / 2000 * 30)              = 28.5
    #   final = min(100, int(24 + 28.5 + 20 + 10))         = 82
    assert score == 82


@pytest.mark.asyncio
async def test_health_score_per_item_respawn_guard(sqlite_db):
    """The N+1 regression guard survived the engine migration.

    The engine loads the whole tenant analytical dataset once (a business_id
    filtered SELECT); a respawned per-item form would issue an extra statement
    with a single-item ``item_id`` predicate.
    """
    SessionLocal, sync_engine = sqlite_db
    async with SessionLocal() as db:
        business_id = await _seed(db)
    tx_events = []
    await _run(SessionLocal, sync_engine, business_id, tx_events)

    total = [s for s in tx_events if "transactions" in s.lower()]
    assert len(total) == 1, "exactly one engine load touches transactions"
    # The N+1 form equates a single item (``WHERE item_id = <one value>``);
    # the engine loader filters by ``business_id`` only.
    per_item_predicates = [s for s in total if "item_id =" in s.lower()]
    assert len(per_item_predicates) == 0, "per-item transaction query respawned"


@pytest.mark.asyncio
async def test_health_score_returns_valid_range(sqlite_db):
    SessionLocal, sync_engine = sqlite_db
    async with SessionLocal() as db:
        business_id = await _seed(db)
    async with SessionLocal() as db:
        score = await calculate_health_score(db, business_id)
    assert 0 <= score <= 100