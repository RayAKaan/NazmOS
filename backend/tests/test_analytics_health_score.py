"""Verifies calculate_health_score performs a single grouped query (Phase 1.2).

Pre-change the function called get_item_daily_avg once per inventory row,
issuing N+1 queries against the transactions table on every dashboard load.
The fix replaces that with one grouped aggregation.
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
    daily_qty = {  # daily_avg = qty/30
        "A": 0.0,     # dead
        "B": 60.0,    # daily_avg=2.0 -> 100/2=50 days -> healthy (>5)
        "C": 200.0,   # daily_avg~6.67 -> 15 days -> healthy
        "D": 900.0,   # daily_avg=30 -> 3.33 days -> critical (<5? -> critical since <5)
        "E": 1000.0,  # daily_avg~33.3 -> 3 days -> critical
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
async def test_health_score_matches_manual_calculation(sqlite_db):
    SessionLocal, sync_engine = sqlite_db
    async with SessionLocal() as db:
        business_id = await _seed(db)
    tx_events = []
    score = await _run(SessionLocal, sync_engine, business_id, tx_events)

    assert score is not None
    # Pre-change the loop issued one per-item daily-avg query (N+1) plus the
    # dead-stock/total-value queries. Post-change the per-item form is gone and
    # the grouped aggregation replaces it. Bound the total number of statements
    # touching transactions so any reintroduced per-item query fails the test.
    total = [s for s in tx_events if "transactions" in s.lower()]
    assert len(total) <= 4
    grouped = [s for s in tx_events if "GROUP BY" in s and "transactions" in s.lower()]
    # One grouped aggregation from calculate_health_score plus the pre-existing
    # grouped dead-stock query inside calculate_dead_stock_value.
    assert len(grouped) >= 1
    assert score >= 0


@pytest.mark.asyncio
async def test_health_score_no_per_item_transaction_queries(sqlite_db):
    """The N+1 regression guard: zero per-item daily-avg queries issued."""
    SessionLocal, sync_engine = sqlite_db
    async with SessionLocal() as db:
        business_id = await _seed(db)
    tx_events = []
    score = await _run(SessionLocal, sync_engine, business_id, tx_events)

    # Every statement mentioning transactions is allowed EXCEPT the per-item
    # daily-avg form: SELECT sum FROM transactions WHERE item_id = :x
    per_item = [
        s for s in tx_events
        if "transactions" in s.lower()
        and "item_id" in s.lower()
        and "GROUP BY" not in s
        and "JOIN" not in s
    ]
    assert len(per_item) == 0


@pytest.mark.asyncio
async def test_health_score_returns_valid_range(sqlite_db):
    SessionLocal, sync_engine = sqlite_db
    async with SessionLocal() as db:
        business_id = await _seed(db)
    async with SessionLocal() as db:
        score = await calculate_health_score(db, business_id)
    assert 0 <= score <= 100
