import uuid
from datetime import date, timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _profit(quantity: int, unit_price: float, cost_price: float) -> float:
    return round(quantity * (unit_price - cost_price), 2)


async def _seed_forecast_data(db_session: AsyncSession, business_id: str) -> str:
    """Insert an item, inventory, and 14 days of transactions for forecasting."""
    item_id = str(uuid.uuid4())
    category_id = str(uuid.uuid4())
    await db_session.execute(
        text("""
            INSERT INTO categories (id, business_id, name, description, sort_order, is_active, created_at)
            VALUES (:id, :business_id, 'Beverages', NULL, 0, true, NOW())
        """),
        {"id": category_id, "business_id": business_id},
    )
    await db_session.execute(
        text("""
            INSERT INTO items (id, business_id, category_id, name, sku, unit, cost_price, sell_price, is_active, created_at)
            VALUES (:id, :business_id, :category_id, 'Test Coffee', 'TCF-001', 'piece', 15, 25, true, NOW())
        """),
        {"id": item_id, "business_id": business_id, "category_id": category_id},
    )
    await db_session.execute(
        text("""
            INSERT INTO inventory (id, business_id, item_id, current_stock, reorder_level, max_stock, created_at)
            VALUES (:id, :business_id, :item_id, 50, 10, 100, NOW())
        """),
        {"id": str(uuid.uuid4()), "business_id": business_id, "item_id": item_id},
    )

    base_date = date(2026, 7, 1)
    for i in range(14):
        quantity = (i % 5) + 1
        unit_price = 25.0
        cost_price = 15.0
        total = round(quantity * unit_price, 2)
        await db_session.execute(
            text("""
                INSERT INTO transactions
                    (id, business_id, item_id, quantity, unit_price, cost_price, total_amount, profit, transaction_at, transaction_type, created_at)
                VALUES
                    (:id, :business_id, :item_id, :quantity, :unit_price, :cost_price, :total_amount, :profit, :transaction_at, 'sale', NOW())
            """),
            {
                "id": str(uuid.uuid4()),
                "business_id": business_id,
                "item_id": item_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "cost_price": cost_price,
                "total_amount": total,
                "profit": _profit(quantity, unit_price, cost_price),
                "transaction_at": base_date + timedelta(days=i),
            },
        )
    await db_session.commit()
    return item_id


@pytest.mark.asyncio
async def test_forecast_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/forecast/",
        params={"business_id": "00000000-0000-0000-0000-000000000001", "item_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_forecast_basic(authenticated_client: dict, db_session: AsyncSession):
    ac = authenticated_client
    item_id = await _seed_forecast_data(db_session, ac["business_id"])

    response = await ac["client"].post(
        "/api/v1/forecast/",
        params={"business_id": ac["business_id"], "item_id": item_id, "days": 30},
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "forecast" in data
    assert "forecast_7d" in data["forecast"] or "forecast_30d" in data["forecast"]


@pytest.mark.asyncio
async def test_forecast_invalid_days(authenticated_client: dict):
    ac = authenticated_client
    response = await ac["client"].post(
        "/api/v1/forecast/",
        params={"business_id": ac["business_id"], "item_id": "00000000-0000-0000-0000-000000000001", "days": 0},
        headers=ac["headers"],
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_forecast_fallback_when_no_history(authenticated_client: dict, db_session: AsyncSession):
    ac = authenticated_client
    # Item exists but has no transactions -> endpoint returns fallback forecast.
    item_id = str(uuid.uuid4())
    await db_session.execute(
        text("""
            INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active, created_at)
            VALUES (:id, :business_id, 'Empty Item', 'EMPTY-001', 'piece', 10, 20, true, NOW())
        """),
        {"id": item_id, "business_id": ac["business_id"]},
    )
    await db_session.commit()

    response = await ac["client"].get(
        f"/api/v1/forecast/{item_id}",
        params={"business_id": ac["business_id"], "horizon": 7},
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "forecast_7d" in data
    assert data["from_cache"] is False


@pytest.mark.asyncio
async def test_get_all_forecasts(authenticated_client: dict):
    ac = authenticated_client
    response = await ac["client"].get(
        f"/api/v1/forecast/all/{ac['business_id']}",
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "forecasts" in data
    assert "total" in data
