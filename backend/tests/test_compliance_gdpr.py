"""GDPR / PDPL compliance endpoint tests.

These tests exercise the data-export, scheduled-deletion, cancellation, and
immediate-deletion flows. They require a Postgres test database and are
skipped automatically when it is unavailable.
"""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


async def test_export_business_data(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.get(
        f"/api/v1/compliance/export/{business_id}",
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["business_id"] == business_id
    assert "items" in data["data"]
    assert "audit_log" in data["data"]
    assert "exported_at" in data


async def test_request_deletion_schedules_purge(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/compliance/delete/{business_id}",
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "scheduled"
    assert data["scheduled_purge_at"] is not None

    # Business is deactivated during the grace period.
    current = await client.get("/api/v1/businesses/current", headers=ctx["headers"])
    assert current.status_code == 404


async def test_cancel_deletion_reactivates_business(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    schedule_response = await client.post(
        f"/api/v1/compliance/delete/{business_id}",
        headers=ctx["headers"],
    )
    assert schedule_response.status_code == 200

    cancel_response = await client.delete(
        f"/api/v1/compliance/delete/{business_id}",
        headers=ctx["headers"],
    )
    assert cancel_response.status_code == 204, cancel_response.text

    current = await client.get("/api/v1/businesses/current", headers=ctx["headers"])
    assert current.status_code == 200
    assert not current.json()["name"].startswith("[PENDING_DELETION]")


async def test_immediate_deletion_purges_business(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/compliance/delete/{business_id}?immediate=true",
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"

    current = await client.get("/api/v1/businesses/current", headers=ctx["headers"])
    assert current.status_code == 404
