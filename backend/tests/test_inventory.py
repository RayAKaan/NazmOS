import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_inventory(client: AsyncClient):
    demo_response = await client.post("/api/v1/auth/demo")
    token = demo_response.json()["access_token"]
    
    response = await client.get(
        f"/api/v1/inventory?business_id={demo_response.json()['user']['id']}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "pagination" in data
    assert "summary" in data
