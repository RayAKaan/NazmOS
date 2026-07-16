import pytest
from httpx import AsyncClient


@pytest.fixture
def auth_headers(client: AsyncClient):
    async def _get_headers():
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "chat_test@example.com",
                "password": "testpass123",
                "full_name": "Chat Test User"
            }
        )
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "chat_test@example.com",
                "password": "testpass123"
            }
        )
        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    import asyncio
    return asyncio.run(_get_headers())


@pytest.mark.asyncio
async def test_chat_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/chat/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "message": "What should I restock?"
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_basic_message(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/chat/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "message": "What should I restock?"
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data or "message_id" in data
    assert "content" in data or "response" in data


@pytest.mark.asyncio
async def test_chat_with_context(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/chat/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "message": "Give me a sales report",
            "include_inventory": True,
            "include_sales": True
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_chat_history(client: AsyncClient, auth_headers):
    await client.post(
        "/api/v1/chat/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "message": "Hello"
        },
        headers=auth_headers
    )
    
    response = await client.get(
        "/api/v1/chat/history",
        params={"business_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data or "messages" in data


@pytest.mark.asyncio
async def test_chat_sse_stream(client: AsyncClient, auth_headers):
    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "message": "Tell me about my inventory"
        },
        headers=auth_headers
    ) as response:
        assert response.status_code == 200
        
        chunks = []
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                chunks.append(line[5:].strip())
        
        assert len(chunks) > 0


@pytest.mark.asyncio
async def test_clear_chat_session(client: AsyncClient, auth_headers):
    session_response = await client.post(
        "/api/v1/chat/",
        json={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "message": "Test message"
        },
        headers=auth_headers
    )
    
    if session_response.status_code == 200:
        session_id = session_response.json().get("session_id")
        
        clear_response = await client.delete(
            f"/api/v1/chat/sessions/{session_id}",
            headers=auth_headers
        )
        
        assert clear_response.status_code == 200
