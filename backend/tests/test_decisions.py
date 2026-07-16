import pytest
from httpx import AsyncClient


@pytest.fixture
def auth_headers(client: AsyncClient):
    async def _get_headers():
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "decision_test@example.com",
                "password": "testpass123",
                "full_name": "Decision Test User"
            }
        )
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "decision_test@example.com",
                "password": "testpass123"
            }
        )
        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    import asyncio
    return asyncio.run(_get_headers())


@pytest.mark.asyncio
async def test_decisions_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/decisions/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "query": "What decisions should I make?"
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_decisions(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/decisions/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "query": "What should I restock this week?"
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "decisions" in data


@pytest.mark.asyncio
async def test_get_decision_history(client: AsyncClient, auth_headers):
    await client.post(
        "/api/v1/decisions/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "query": "Show me recommendations"
        },
        headers=auth_headers
    )
    
    response = await client.get(
        "/api/v1/decisions/history",
        params={"business_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "decisions" in data or "items" in data


@pytest.mark.asyncio
async def test_update_decision_status(client: AsyncClient, auth_headers):
    decision_response = await client.post(
        "/api/v1/decisions/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "query": "What should I do?"
        },
        headers=auth_headers
    )
    
    if decision_response.status_code == 200:
        decisions = decision_response.json().get("decisions", [])
        if decisions:
            decision_id = decisions[0].get("id")
            
            update_response = await client.patch(
                f"/api/v1/decisions/{decision_id}",
                json={"status": "accepted"},
                headers=auth_headers
            )
            
            assert update_response.status_code == 200


@pytest.mark.asyncio
async def test_decision_stats(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/v1/decisions/stats",
        params={"business_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "total_decisions" in data or "by_priority" in data


@pytest.mark.asyncio
async def test_decision_pagination(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/v1/decisions/history",
        params={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "page": 1,
            "limit": 10
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "pagination" in data or "items" in data
