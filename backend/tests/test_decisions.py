import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_decisions_recommend_requires_auth(client: AsyncClient):
    response = await client.get(
        "/api/v1/decisions/recommend",
        params={"business_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_decisions(authenticated_client: dict):
    ac = authenticated_client
    response = await ac["client"].get(
        "/api/v1/decisions/recommend",
        params={"business_id": ac["business_id"]},
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert "decisions" in data
    assert "summary" in data


@pytest.mark.asyncio
async def test_apply_decision(authenticated_client: dict):
    ac = authenticated_client
    decision_id = str(uuid.uuid4())
    response = await ac["client"].post(
        f"/api/v1/decisions/apply/{decision_id}",
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "applied"
    assert data["decision_id"] == decision_id
