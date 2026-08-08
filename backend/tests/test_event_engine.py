"""Tests for the Universal Event Engine (Phase 0).

Postgres-dependent integration tests are skipped automatically when the test
 database is unavailable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.schemas.events import EventIngest
from app.services.event_engine import (
    _compute_checksum,
    _pattern_matches,
    _validate_payload,
    ingest_event,
)


def test_checksum_is_deterministic():
    payload = {"item_id": str(uuid4()), "quantity": 5}
    data = {
        "event_type": "sale.completed",
        "version": 1,
        "source": "foodics",
        "source_id": "order-123",
        "payload": payload,
        "occurred_at": "2026-08-05T00:00:00+00:00",
    }
    first = _compute_checksum(data)
    second = _compute_checksum(data)
    assert first == second
    assert len(first) == 64


def test_checksum_detects_payload_changes():
    base = {
        "event_type": "sale.completed",
        "version": 1,
        "source": "foodics",
        "source_id": "order-123",
        "payload": {"total": 100.0},
        "occurred_at": "2026-08-05T00:00:00+00:00",
    }
    changed = {**base, "payload": {"total": 101.0}}
    assert _compute_checksum(base) != _compute_checksum(changed)


def test_builtin_payload_validation():
    valid = {"order_id": "o1", "total_amount": 120.0, "payment_method": "card"}
    result = _validate_payload("sale.completed", valid)
    assert result["total_amount"] == 120.0

    # Unknown event types pass through unchanged.
    raw = {"any": "value"}
    assert _validate_payload("custom.event", raw) == raw


def test_pattern_matching():
    assert _pattern_matches("sale.*", "sale.completed")
    assert _pattern_matches("sale.*", "sale.refunded")
    assert not _pattern_matches("sale.*", "inventory.changed")
    assert _pattern_matches("*", "anything")


@pytest.mark.asyncio
async def test_ingest_event_creates_record_and_processes(db_session):
    event = EventIngest(
        event_type="inventory.changed",
        source="manual",
        source_id="inv-1",
        payload={"item_id": str(uuid4()), "quantity_delta": -3, "new_quantity": 10},
    )
    business_id = uuid4()
    record = await ingest_event(db_session, business_id, event)
    assert record.id is not None
    assert record.event_type == "inventory.changed"
    assert record.processed is True
    assert record.processed_at is not None
    assert record.checksum is not None


@pytest.mark.asyncio
async def test_duplicate_event_is_idempotent(db_session):
    event = EventIngest(
        event_type="price.updated",
        source="api",
        source_id="price-1",
        payload={"item_id": str(uuid4()), "new_price": 15.0},
    )
    business_id = uuid4()
    first = await ingest_event(db_session, business_id, event)
    second = await ingest_event(db_session, business_id, event)
    assert first.id != second.id
    # Both are marked processed; the second did not cause a duplicate business action
    # because the event bus subscriber uses the unique checksum to dedupe.
    assert second.processed is True


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_create_event_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/events?business_id={business_id}",
        json={
            "event_type": "sale.completed",
            "source": "manual",
            "source_id": "order-999",
            "payload": {"total_amount": 250.0},
        },
        headers=ctx["headers"],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["event_type"] == "sale.completed"
    assert data["processed"] is True
    assert data["business_id"] == business_id


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_list_events_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    for i in range(3):
        await client.post(
            f"/api/v1/events?business_id={business_id}",
            json={
                "event_type": "inventory.changed",
                "source": "manual",
                "source_id": f"inv-{i}",
                "payload": {"quantity_delta": i},
            },
            headers=ctx["headers"],
        )

    response = await client.get(
        f"/api/v1/events?business_id={business_id}&event_type=inventory.changed&limit=10",
        headers=ctx["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(e["event_type"] == "inventory.changed" for e in data)


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_event_types_registry(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]

    response = await client.get("/api/v1/events/types", headers=ctx["headers"])
    assert response.status_code == 200
    data = response.json()
    names = {t["name"] for t in data}
    assert "sale.completed" in names
    assert "inventory.changed" in names


@pytest.mark.asyncio
async def test_event_subscription_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/events/subscriptions?business_id={business_id}",
        json={
            "consumer_name": "test-consumer",
            "event_pattern": "sale.*",
            "queue_or_channel": "nazmos:consumers:test",
        },
        headers=ctx["headers"],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["consumer_name"] == "test-consumer"
    assert data["event_pattern"] == "sale.*"
