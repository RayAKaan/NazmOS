"""Verifies get_dead_stock issues a single query (Phase 1.3).

Pre-change the function ran three extra queries (Inventory, Item, Category)
inside the per-row loop. The fix folds those columns into the outer joined
query so only one statement executes.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import (
    Base,
    Business,
    Category,
    Inventory,
    Item,
    Transaction,
)
from app.services.analytics_service import get_dead_stock


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


async def _seed(db: AsyncSession) -> uuid.UUID:
    business = Business(id=uuid.uuid4(), name="Dead Stock Test", type="baqala")
    cat = Category(id=uuid.uuid4(), business_id=business.id, name="Dairy")
    db.add_all([business, cat])
    await db.flush()

    # Three items, all with a sale older than the dead-stock window.
    items = [
        Item(id=uuid.uuid4(), business_id=business.id, category_id=cat.id,
             name="ItemA", cost_price=2.0, sell_price=3.0),
        Item(id=uuid.uuid4(), business_id=business.id, category_id=cat.id,
             name="ItemB", cost_price=5.0, sell_price=7.0),
        Item(id=uuid.uuid4(), business_id=business.id, category_id=None,
             name="ItemC", cost_price=1.0, sell_price=1.5),
    ]
    db.add_all(items)
    await db.flush()

    for item in items:
        db.add(Inventory(
            id=uuid.uuid4(),
            business_id=business.id,
            item_id=item.id,
            current_stock=20,
        ))
    await db.flush()

    now = datetime.now(timezone.utc)
    # ItemA: sold 62 days ago -> remove. ItemB: sold 50 days ago -> discount.
    # ItemC: no transactions at all -> dead via the null/coalesce path.
    db.add_all([
        Transaction(
            id=uuid.uuid4(), business_id=business.id, item_id=items[0].id,
            quantity=2, unit_price=3.0, cost_price=2.0, total_amount=6.0,
            profit=2.0, transaction_at=now - timedelta(days=62),
        ),
        Transaction(
            id=uuid.uuid4(), business_id=business.id, item_id=items[1].id,
            quantity=3, unit_price=7.0, cost_price=5.0, total_amount=21.0,
            profit=6.0, transaction_at=now - timedelta(days=50),
        ),
    ])
    await db.commit()
    return business.id


@pytest.mark.asyncio
async def test_dead_stock_single_query_and_correct_results(sqlite_db):
    SessionLocal, sync_engine = sqlite_db
    async with SessionLocal() as db:
        business_id = await _seed(db)

        statements = []

        @event.listens_for(sync_engine, "before_cursor_execute")
        def _count(conn, cursor, statement, parameters, context, executemany):
            if "transactions" in statement.lower():
                statements.append(statement)

        try:
            response = await get_dead_stock(db, business_id)
        finally:
            event.remove(sync_engine, "before_cursor_execute", _count)

    assert len(statements) == 1

    assert response.total_stuck_value == pytest.approx(
        20 * 2.0 + 20 * 5.0 + 20 * 1.0
    )
    by_name = {item.name: item for item in response.items}
    assert set(by_name) == {"ItemA", "ItemB", "ItemC"}

    # ItemA: 62 days since last sale -> remove.
    assert by_name["ItemA"].recommendation == "remove"
    assert by_name["ItemA"].category == "Dairy"
    assert by_name["ItemA"].days_since_last_sale >= 30

    # ItemB: 40 days -> discount.
    assert by_name["ItemB"].recommendation == "discount"
    assert by_name["ItemB"].category == "Dairy"

    # ItemC: no sales -> dead, uncategorized.
    assert by_name["ItemC"].recommendation in {"remove", "discount", "bundle"}
    assert by_name["ItemC"].category == "Uncategorized"
    assert by_name["ItemC"].current_stock == 20


@pytest.mark.asyncio
async def test_dead_stock_empty_returns_empty(sqlite_db):
    SessionLocal, sync_engine = sqlite_db
    async with SessionLocal() as db:
        business = Business(id=uuid.uuid4(), name="Empty", type="baqala")
        db.add(business)
        await db.commit()
        response = await get_dead_stock(db, business.id)

    assert response.items == []
    assert response.total_stuck_value == 0
