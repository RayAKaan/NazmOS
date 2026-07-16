import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_demo_login(client: AsyncClient):
    response = await client.post("/api/v1/auth/demo")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "demo@nazmos.ai"


@pytest.mark.asyncio
async def test_get_dashboard_summary(client: AsyncClient):
    demo_response = await client.post("/api/v1/auth/demo")
    token = demo_response.json()["access_token"]
    
    response = await client.get(
        f"/api/v1/dashboard/summary?business_id={demo_response.json()['user']['id']}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "today" in data
    assert "this_month" in data
    assert "health_score" in data


@pytest.mark.asyncio
async def test_get_sales_trend(client: AsyncClient):
    demo_response = await client.post("/api/v1/auth/demo")
    token = demo_response.json()["access_token"]
    
    response = await client.get(
        f"/api/v1/dashboard/sales-trend?business_id={demo_response.json()['user']['id']}&period=30",
        headers={"Authorization": f"Bearer {token}"}
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
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
