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
        params={"business_id": ac["business_id"]},
        headers=ac["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "applied"
    assert data["decision_id"] == decision_id


@pytest.mark.asyncio
async def test_apply_decision_requires_business_scoped_access(authenticated_client: dict):
    """The 'apply' write must not touch a decision the caller does not own.

    The row-lock SQL is now double-bound to the caller's business_id, so a
    foreign/nonexistent decision is silently not applied (200, no row) and the
    endpoint rejects a caller who passes another tenant's business_id.
    """
    ac = authenticated_client
    decision_id = str(uuid.uuid4())
    foreign_business = str(uuid.uuid4())

    # Caller cannot assert access on a business they do not belong to.
    response = await ac["client"].post(
        f"/api/v1/decisions/apply/{decision_id}",
        params={"business_id": foreign_business},
        headers=ac["headers"],
    )
    assert response.status_code in (403, 404)

    # A missing decision under the caller's own business is a no-op (200).
    response = await ac["client"].post(
        f"/api/v1/decisions/apply/{decision_id}",
        params={"business_id": ac["business_id"]},
        headers=ac["headers"],
    )
    assert response.status_code == 200
