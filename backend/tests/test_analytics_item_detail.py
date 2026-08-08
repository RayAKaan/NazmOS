"""Regression test for the get_item_detail NameError (Phase 1.1).

Pre-change the function referenced a local named ``status`` (lines 899-908)
but constructed the response with ``computed_status`` (line 953), which was
only defined inside get_inventory_list — every item-detail request raised
NameError. The fix renames the local to ``computed_status``.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base, Business, Inventory, Item, Transaction
from app.services.analytics_service import get_item_detail


@pytest_asyncio.fixture
async def sqlite_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield SessionLocal
    finally:
        await engine.dispose()


async def _seed(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    business = Business(id=uuid.uuid4(), name="Test Baqala", type="baqala")
    item = Item(
        id=uuid.uuid4(),
        business_id=business.id,
        name="Milk 1L",
        cost_price=4.5,
        sell_price=6.0,
        sku="SKU-001",
    )
    inventory = Inventory(
        id=uuid.uuid4(),
        business_id=business.id,
        item_id=item.id,
        current_stock=50,
        reorder_level=10,
        max_stock=100,
    )
    db.add_all([business, item, inventory])
    await db.commit()
    return business.id, item.id


@pytest.mark.asyncio
async def test_item_detail_returns_status_without_nameerror(sqlite_db):
    SessionLocal = sqlite_db
    async with SessionLocal() as db:
        business_id, item_id = await _seed(db)

        result = await get_item_detail(db, business_id, item_id)

        assert result is not None
        assert result.item.status in {"dead", "critical", "low", "healthy"}


@pytest.mark.asyncio
async def test_item_detail_dead_stock_status(sqlite_db):
    SessionLocal = sqlite_db
    async with SessionLocal() as db:
        business_id, item_id = await _seed(db)
        # Zero sales in the last 30 days -> daily_avg < 0.1 -> dead.
        old = datetime.now(timezone.utc) - timedelta(days=60)
        tx = Transaction(
            id=uuid.uuid4(),
            business_id=business_id,
            item_id=item_id,
            quantity=5,
            unit_price=6.0,
            cost_price=4.5,
            total_amount=30.0,
            profit=7.5,
            transaction_at=old,
        )
        db.add(tx)
        await db.commit()

        result = await get_item_detail(db, business_id, item_id)

        assert result is not None
        assert result.item.status == "dead"


@pytest.mark.asyncio
async def test_item_detail_missing_item_returns_none(sqlite_db):
    SessionLocal = sqlite_db
    async with SessionLocal() as db:
        result = await get_item_detail(db, uuid.uuid4(), uuid.uuid4())
        assert result is None
