import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_inventory_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/inventory?business_id=00000000-0000-0000-0000-000000000001")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_inventory_for_business(authenticated_client: dict):
    ac = authenticated_client
    response = await ac["client"].get(
        f"/api/v1/inventory?business_id={ac['business_id']}",
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "pagination" in data
    assert "summary" in data
