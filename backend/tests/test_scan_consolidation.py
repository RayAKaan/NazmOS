"""WS5 — scan consolidation contract.

Dead-stock appears through two public surfaces:
  - agent tool ``get_dead_stock_summary`` (agent_tools.py)   → per-item rows
  - ``analytics.calculate_dead_stock_value`` (analytics_service.py) → total SAR

Both MUST implement the same canonical rule (FINANCIAL_VOCABULARY_ADR + goal
domain "dead_stock_value"): an item is dead when it has fewer than one unit of
sales in the last ``days`` days and still has stock; stuck value is
``current_stock * cost_price``.  These tests pin that contract so a future
drift in one scan fails loudly.
"""
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from tests.fixtures.merchants import seed_recurring_stockout_merchant


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


async def test_scan_surfaces_agree_on_dead_stock(db):
    """Seed: 3 dead items (no sales, stock>0) + 1 fast mover (daily sales).

    Both scans must flag exactly the 3 dead items and agree on stuck value
    (stock * cost) — top-10 limit not exceeded so totals match.
    """
    from app.services.agent_tools import execute_agent_tool
    from app.services.analytics_service import calculate_dead_stock_value

    info = await seed_recurring_stockout_merchant(db)
    bid = info["business_id"]
    cat = info["category_id"]

    dead = []
    for name, stock, cost, sell in (
        ("Dead A", 10.0, 2000.0, 2800.0),
        ("Dead B", 4.0, 500.0, 700.0),
        ("Dead C", 2.0, 50.0, 80.0),
    ):
        from tests.fixtures.merchants import seed_item, seed_inventory

        iid = await seed_item(db, bid, name, cat, cost=cost, sell=sell)
        await seed_inventory(db, bid, iid, stock=stock)
        dead.append((name, stock * cost))
    await db.commit()

    tool = await execute_agent_tool("get_dead_stock_summary", {"days_no_sale": 30}, bid, db)
    tool_items = {r["name"] for r in tool["dead_stock_items"]}
    assert tool_items == {"Dead A", "Dead B", "Dead C"}, tool_items
    assert "Fresh Milk 1L" not in tool_items, "fast mover must not be flagged"
    tool_total = sum(float(r["stuck_sar"]) for r in tool["dead_stock_items"])
    assert round(tool["total_stuck_sar"], 2) == round(tool_total, 2)

    analytics_total = await calculate_dead_stock_value(db, bid)
    expected = round(sum(s for _, s in dead), 2)
    assert float(analytics_total) == expected, "analytics total must equal stock*cost of dead items"
    assert round(tool["total_stuck_sar"], 2) == float(analytics_total), \
        "agent tool and analytics scan must agree on total dead-stock SAR"


async def test_dead_scan_requires_zero_sales(db):
    """An item with ANY recent sale is not dead; the rule is qty_30d < 1."""
    from datetime import timedelta

    from app.services.agent_tools import execute_agent_tool
    from app.services.analytics_service import calculate_dead_stock_value
    from app.utils.clock import utcnow
    from tests.fixtures.merchants import seed_item, seed_inventory, seed_transactions

    info = await seed_recurring_stockout_merchant(db)
    bid = info["business_id"]
    cat = info["category_id"]

    moving = await seed_item(db, bid, "Sold Once", cat, cost=10.0, sell=20.0)
    await seed_inventory(db, bid, moving, stock=50.0)
    await seed_transactions(db, bid, moving, 1.0, utcnow() - timedelta(days=3))
    await db.commit()

    tool = await execute_agent_tool("get_dead_stock_summary", {"days_no_sale": 30}, bid, db)
    assert "Sold Once" not in {r["name"] for r in tool["dead_stock_items"]}
    not_dead_total = await calculate_dead_stock_value(db, bid)
    assert float(not_dead_total) == 0.0, "a single sale removes the item from the dead scan"