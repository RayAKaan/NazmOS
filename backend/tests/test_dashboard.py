import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dashboard_summary_requires_auth(client: AsyncClient):
    response = await client.get(
        "/api/v1/dashboard/summary?business_id=00000000-0000-0000-0000-000000000001"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_dashboard_summary(authenticated_client: dict):
    ac = authenticated_client
    response = await ac["client"].get(
        f"/api/v1/dashboard/summary?business_id={ac['business_id']}",
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "today" in data
    assert "this_month" in data
    assert "health_score" in data


@pytest.mark.asyncio
async def test_get_sales_trend(authenticated_client: dict):
    ac = authenticated_client
    response = await ac["client"].get(
        f"/api/v1/dashboard/sales-trend?business_id={ac['business_id']}&period=30",
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "summary" in data


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["version"] == "1.0.0"
    assert "checks" in data
