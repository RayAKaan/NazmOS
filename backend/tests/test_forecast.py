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


def _iter_effective_routes(app):
    """Yield the app's real routes, descending into included-router wrappers.

    ``app.routes`` is not a flat list of APIRoute objects across FastAPI
    versions: 0.141 (starlette 1.4) wraps each ``include_router`` result in an
    ``_IncludedRouter`` whose own ``path``/``methods`` are None and whose routes
    hang off ``original_router``. Older versions put the APIRoute objects
    directly in ``app.routes``. The duplicate-registration pin below must see
    the real route table either way, so normalise both shapes here.
    """
    for route in app.routes:
        if getattr(route, "path", None) is not None:
            yield route
            continue
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _iter_effective_routes(inner)
            continue
        inner_routes = getattr(route, "routes", None)
        if inner_routes:
            yield from _iter_effective_routes(type("R", (), {"routes": inner_routes})())


async def test_get_all_forecasts_route_unique_in_router_and_openapi():
    # Phase 2B 6/13 pin: exactly ONE GET /all/{business_id} in BOTH the
    # forecast router's route table and the mounted OpenAPI schema.
    # forecast.py previously registered the same GET /all/{business_id} twice
    # (handler at :123 canonical, :241 dead shadow). Only the first-registered
    # route is reachable in Starlette, so :241 was unreachable dead code -
    # Phase 2B 6 removed it :241 and this test fails CI if the dedup regresses.
    from app.routers.forecast import router as forecast_router

    # Note: this forecast router registers FULL-prefixed paths (the router is
    # declared with the /api/v1/forecast prefix baked in, so route.path here is
    # "/api/v1/forecast/all/{business_id}", not the bare "/all/{business_id}".
    matched = [
        r for r in forecast_router.routes
        if getattr(r, "path", None) == "/api/v1/forecast/all/{business_id}"
        and "GET" in (getattr(r, "methods", None) or set())
    ]
    assert len(matched) == 1, (
        "expected exactly ONE GET /api/v1/forecast/all/{business_id} "
        f"registration on the forecast router, found {len(matched)}"
    )

    from app.main import app

    app_matched = [
        r for r in _iter_effective_routes(app)
        if getattr(r, "path", None) == "/api/v1/forecast/all/{business_id}"
        and "GET" in (getattr(r, "methods", None) or set())
    ]
    assert len(app_matched) == 1, (
        "expected exactly ONE app-level GET /all/{business_id}, found "
        f"{len(app_matched)}"
    )

    openapi_paths = app.openapi().get("paths", {}).get(
        "/api/v1/forecast/all/{business_id}", {}
    )
    assert "get" in openapi_paths, "OpenAPI must still expose the GET /all route"
    assert openapi_paths["get"]["operationId"].startswith("get_all_forecasts"), (
        "single canonical operationId (prefix get_all_forecasts) after dedup, "
        f"got {openapi_paths['get']['operationId']}"
    )
