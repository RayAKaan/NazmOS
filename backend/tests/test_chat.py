import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/chat/",
        params={
            "business_id": "00000000-0000-0000-0000-000000000001",
            "message": "What should I restock?",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_streaming_response(authenticated_client: dict):
    ac = authenticated_client
    async with ac["client"].stream(
        "POST",
        "/api/v1/chat/",
        params={
            "business_id": ac["business_id"],
            "message": "What should I restock?",
        },
        headers=ac["headers"],
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        chunks = []
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                chunks.append(line[5:].strip())
        assert len(chunks) > 0


@pytest.mark.asyncio
async def test_get_chat_sessions(authenticated_client: dict):
    ac = authenticated_client
    # Create a session first via the streaming endpoint.
    async with ac["client"].stream(
        "POST",
        "/api/v1/chat/",
        params={
            "business_id": ac["business_id"],
            "message": "Hello",
        },
        headers=ac["headers"],
    ) as response:
        assert response.status_code == 200

    response = await ac["client"].get(
        "/api/v1/chat/sessions",
        params={"business_id": ac["business_id"]},
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data


@pytest.mark.asyncio
async def test_get_chat_suggestions(authenticated_client: dict):
    ac = authenticated_client
    response = await ac["client"].get(
        "/api/v1/chat/suggestions",
        params={"business_id": ac["business_id"]},
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "suggestions" in data
