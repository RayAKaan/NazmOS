import pytest
from httpx import AsyncClient


@pytest.fixture
def auth_headers(client: AsyncClient):
    async def _get_headers():
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "forecast_test@example.com",
                "password": "testpass123",
                "full_name": "Forecast Test User"
            }
        )
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "forecast_test@example.com",
                "password": "testpass123"
            }
        )
        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    import asyncio
    return asyncio.run(_get_headers())


@pytest.mark.asyncio
async def test_forecast_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/forecast/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "days": 30
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_forecast_basic(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/forecast/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "days": 30
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "forecasts" in data or "predictions" in data


@pytest.mark.asyncio
async def test_forecast_with_categories(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/forecast/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "days": 30,
            "categories": ["Dairy", "Bakery"]
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_forecast_by_product(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/forecast/product",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "days": 30
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "forecasts" in data


@pytest.mark.asyncio
async def test_forecast_invalid_days(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/forecast/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "days": 0
        },
        headers=auth_headers
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_forecast_days_limit(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/forecast/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "days": 365
        },
        headers=auth_headers
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_forecast_cache(client: AsyncClient, auth_headers):
    await client.post(
        "/api/v1/forecast/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "days": 30
        },
        headers=auth_headers
    )
    
    response = await client.get(
        "/api/v1/forecast/cache",
        params={"business_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_forecast_summary(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/v1/forecast/summary",
        params={"business_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "total_products" in data or "summary" in data
