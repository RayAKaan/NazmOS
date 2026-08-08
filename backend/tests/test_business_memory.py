"""Tests for the Business Memory Engine (Phase 1).

Postgres-dependent integration tests are skipped automatically when the test
database is unavailable. SQLite-backed integration tests run the projector and
replay logic locally.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4, UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base, BusinessMemory, Event, MemoryType
from app.schemas.business_memory import GoalSetRequest
from app.services.business_memory import (
    _deep_delta,
    _get_path,
    _set_path,
    _to_uuid,
    get_memory,
    get_or_create_memory,
    list_memory_changes,
    replay_events_to_memory,
    route_event_to_projectors,
    set_goals,
    set_memory_path,
)


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests (no DB)
# ═══════════════════════════════════════════════════════════════════════════

def test_to_uuid_normalizes_strings():
    uid = uuid4()
    assert _to_uuid(uid) == uid
    assert _to_uuid(str(uid)) == uid


def test_get_path_reads_nested_values():
    data = {"a": {"b": {"c": 1}}}
    assert _get_path(data, "a.b.c") == 1
    assert _get_path(data, "a.b.missing") is None
    assert _get_path(data, "missing.path") is None


def test_set_path_creates_intermediate_dicts():
    data: dict = {}
    old = _set_path(data, "x.y.z", 42)
    assert old is None
    assert data == {"x": {"y": {"z": 42}}}


def test_set_path_returns_old_value():
    data = {"x": {"y": {"z": 1}}}
    old = _set_path(data, "x.y.z", 2)
    assert old == 1


def test_deep_delta_detects_changes():
    assert _deep_delta(1, 2) is True
    assert _deep_delta({"a": 1}, {"a": 1}) is False
    assert _deep_delta(None, 0) is True


# ═══════════════════════════════════════════════════════════════════════════
# SQLite integration tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session for projector/replay tests."""
    # StaticPool is required for an in-memory SQLite database so all operations
    # share the same underlying connection/database.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_or_create_memory_returns_empty_document(sqlite_session: AsyncSession):
    business_id = uuid4()
    memory = await get_or_create_memory(sqlite_session, business_id, MemoryType.CURRENT_STATE.value)
    assert memory.business_id == business_id
    assert memory.memory_type == MemoryType.CURRENT_STATE.value
    assert memory.data == {}


@pytest.mark.asyncio
async def test_set_memory_path_records_update(sqlite_session: AsyncSession):
    business_id = uuid4()
    update = await set_memory_path(
        sqlite_session,
        business_id,
        MemoryType.CURRENT_STATE.value,
        "inventory.sku123.stock",
        42.0,
    )
    await sqlite_session.commit()

    assert update is not None
    assert update.path == "inventory.sku123.stock"
    assert update.new_value == 42.0

    memory = await get_memory(sqlite_session, business_id, MemoryType.CURRENT_STATE.value)
    assert memory is not None
    assert memory.data["inventory"]["sku123"]["stock"] == 42.0
    assert memory.version == 1


@pytest.mark.asyncio
async def test_set_memory_path_skips_unchanged_values(sqlite_session: AsyncSession):
    business_id = uuid4()
    await set_memory_path(
        sqlite_session,
        business_id,
        MemoryType.CURRENT_STATE.value,
        "inventory.sku123.stock",
        42.0,
    )
    await sqlite_session.commit()

    second = await set_memory_path(
        sqlite_session,
        business_id,
        MemoryType.CURRENT_STATE.value,
        "inventory.sku123.stock",
        42.0,
    )
    assert second is None


@pytest.mark.asyncio
async def test_inventory_changed_projector(sqlite_session: AsyncSession):
    business_id = uuid4()
    event = Event(
        id=uuid4(),
        business_id=business_id,
        event_type="inventory.changed",
        source="manual",
        source_id="inv-1",
        payload={"item_id": "item-abc", "new_quantity": 5.0, "quantity_delta": -3.0, "reason": "sale"},
        checksum="x",
        occurred_at=datetime.now(timezone.utc),
    )
    sqlite_session.add(event)
    await sqlite_session.flush()

    await route_event_to_projectors(sqlite_session, event)
    await sqlite_session.commit()

    memory = await get_memory(sqlite_session, business_id, MemoryType.CURRENT_STATE.value)
    assert memory.data["inventory"]["item-abc"]["stock"] == 5.0
    assert memory.data["inventory"]["item-abc"]["reorder_flag"] is True


@pytest.mark.asyncio
async def test_sale_completed_projector(sqlite_session: AsyncSession):
    business_id = uuid4()
    today = datetime.now(timezone.utc).date().isoformat()
    event = Event(
        id=uuid4(),
        business_id=business_id,
        event_type="sale.completed",
        source="pos",
        source_id="order-1",
        payload={
            "order_id": "order-1",
            "total_amount": 250.0,
            "items": [{"item_id": "item-1", "quantity": 2}],
        },
        checksum="y",
        occurred_at=datetime.now(timezone.utc),
    )
    sqlite_session.add(event)
    await sqlite_session.flush()

    await route_event_to_projectors(sqlite_session, event)
    await sqlite_session.commit()

    current = await get_memory(sqlite_session, business_id, MemoryType.CURRENT_STATE.value)
    assert current.data["sales"]["daily"][today]["total"] == 250.0
    patterns = await get_memory(sqlite_session, business_id, MemoryType.PATTERNS.value)
    assert patterns.data["top_products"]["item-1"]["quantity_30d"] == 2.0


@pytest.mark.asyncio
async def test_price_updated_projector_trims_history(sqlite_session: AsyncSession):
    business_id = uuid4()
    event_ids = []
    for i in range(25):
        event = Event(
            id=uuid4(),
            business_id=business_id,
            event_type="price.updated",
            source="api",
            source_id=f"price-{i}",
            payload={"item_id": "item-x", "new_price": 10.0 + i},
            checksum=f"z{i}",
            occurred_at=datetime.now(timezone.utc),
        )
        sqlite_session.add(event)
        await sqlite_session.flush()
        event_ids.append(event.id)
        await route_event_to_projectors(sqlite_session, event)

    await sqlite_session.commit()

    patterns = await get_memory(sqlite_session, business_id, MemoryType.PATTERNS.value)
    history = patterns.data["pricing"]["item-x"]["history"]
    assert len(history) == 20
    assert history[-1]["price"] == 34.0


@pytest.mark.asyncio
async def test_replay_events_is_deterministic(sqlite_session: AsyncSession):
    """Property test: replaying the same event stream yields the same memory."""
    business_id = uuid4()
    events = []
    for i in range(3):
        event = Event(
            id=uuid4(),
            business_id=business_id,
            event_type="sale.completed",
            source="pos",
            source_id=f"order-{i}",
            payload={"total_amount": 100.0 * (i + 1), "items": []},
            checksum=f"r{i}",
            occurred_at=datetime.now(timezone.utc),
        )
        events.append(event)

    first_run = await replay_events_to_memory(sqlite_session, business_id, events)
    first_total = first_run[MemoryType.CURRENT_STATE.value].data["sales"]["daily"][datetime.now(timezone.utc).date().isoformat()]["total"]

    # Re-run on the same events after clearing memory.
    second_run = await replay_events_to_memory(sqlite_session, business_id, events)
    second_total = second_run[MemoryType.CURRENT_STATE.value].data["sales"]["daily"][datetime.now(timezone.utc).date().isoformat()]["total"]

    assert first_total == second_total
    assert first_total == 600.0


@pytest.mark.asyncio
async def test_set_goals(sqlite_session: AsyncSession):
    business_id = uuid4()
    memory = await set_goals(sqlite_session, business_id, {"profit_target_sar": 50000})
    await sqlite_session.commit()
    assert memory.data["goals"]["profit_target_sar"] == 50000

    updates, total = await list_memory_changes(sqlite_session, business_id, MemoryType.GOALS.value)
    assert total == 1
    assert updates[0].path == "goals"


# ═══════════════════════════════════════════════════════════════════════════
# API integration tests (Postgres only)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_memory_endpoints(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    # Set goals.
    response = await client.patch(
        f"/api/v1/intelligence/memory/goals?business_id={business_id}",
        json={"goals": {"profit_target_sar": 10000}},
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["memory_type"] == "goals"
    assert data["data"]["goals"]["profit_target_sar"] == 10000

    # Read goals back.
    response = await client.get(
        f"/api/v1/intelligence/memory/goals?business_id={business_id}",
        headers=ctx["headers"],
    )
    assert response.status_code == 200
    assert response.json()["data"]["goals"]["profit_target_sar"] == 10000

    # Read changes.
    response = await client.get(
        f"/api/v1/intelligence/memory/changes?business_id={business_id}&memory_type=goals",
        headers=ctx["headers"],
    )
    assert response.status_code == 200
    changes = response.json()
    assert changes["total"] == 1
    assert changes["items"][0]["path"] == "goals"


@pytest.mark.asyncio
async def test_memory_endpoint_rejects_invalid_type(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.get(
        f"/api/v1/intelligence/memory/invalid_type?business_id={business_id}",
        headers=ctx["headers"],
    )
    assert response.status_code == 400
