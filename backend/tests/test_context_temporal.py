"""Tests for the Context & Temporal Reasoning Engine (Phase 3).

Postgres-dependent integration tests are skipped automatically when the test
database is unavailable. SQLite-backed integration tests run the context,
timeline, what-changed, and causal-chain logic locally.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base, BusinessContext, Event, EventDerivation
from app.services.context_engine import build_context_snapshot, create_context, get_active_context
from app.services.event_engine import ingest_event
from app.services.temporal_reasoning import create_derivation, get_timeline, what_changed, why
from app.schemas.events import EventIngest


@pytest_asyncio.fixture(scope="function")
async def sqlite_session() -> AsyncSession:
    """In-memory SQLite session for context/temporal tests."""
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
async def test_create_and_list_context(sqlite_session: AsyncSession):
    business_id = uuid4()
    now = datetime.now(timezone.utc)
    ctx = await create_context(
        sqlite_session,
        business_id,
        {
            "context_type": "holiday",
            "source": "test",
            "effective_from": now,
            "effective_until": now + timedelta(days=1),
            "payload": {"name": "Eid"},
            "confidence": 1.0,
        },
    )
    await sqlite_session.commit()
    assert ctx.context_type == "holiday"

    active = await get_active_context(sqlite_session, business_id, context_type="holiday")
    assert len(active) == 1
    assert active[0].payload["name"] == "Eid"


@pytest.mark.asyncio
async def test_context_snapshot_aggregates_by_type(sqlite_session: AsyncSession):
    business_id = uuid4()
    now = datetime.now(timezone.utc)
    await create_context(sqlite_session, business_id, {
        "context_type": "holiday",
        "effective_from": now,
        "effective_until": now + timedelta(days=1),
        "payload": {"name": "Eid"},
    })
    await create_context(sqlite_session, business_id, {
        "context_type": "weather",
        "effective_from": now,
        "effective_until": now + timedelta(hours=1),
        "payload": {"temperature_c": 40},
    })
    await sqlite_session.commit()

    snapshot = await build_context_snapshot(sqlite_session, business_id)
    assert "holiday" in snapshot
    assert "weather" in snapshot
    assert snapshot["weather"][0]["payload"]["temperature_c"] == 40


@pytest.mark.asyncio
async def test_event_ingestion_attaches_context_snapshot(sqlite_session: AsyncSession):
    business_id = uuid4()
    now = datetime.now(timezone.utc)
    await create_context(sqlite_session, business_id, {
        "context_type": "holiday",
        "effective_from": now,
        "effective_until": now + timedelta(days=1),
        "payload": {"name": "Eid"},
    })
    await sqlite_session.commit()

    event = EventIngest(
        event_type="sale.completed",
        source="pos",
        source_id="order-1",
        payload={"total_amount": 100.0},
    )
    record = await ingest_event(sqlite_session, business_id, event)
    assert record.context_snapshot is not None
    assert "holiday" in record.context_snapshot


@pytest.mark.asyncio
async def test_timeline_query(sqlite_session: AsyncSession):
    business_id = uuid4()
    now = datetime.now(timezone.utc)
    for i in range(3):
        event = Event(
            id=uuid4(),
            business_id=business_id,
            event_type="sale.completed",
            source="pos",
            source_id=f"order-{i}",
            payload={"total_amount": float(i)},
            checksum=f"c{i}",
            occurred_at=now - timedelta(hours=i),
        )
        sqlite_session.add(event)
    await sqlite_session.commit()

    events, total = await get_timeline(sqlite_session, business_id, limit=10)
    assert total == 3
    assert events[0].occurred_at >= events[1].occurred_at


@pytest.mark.asyncio
async def test_what_changed(sqlite_session: AsyncSession):
    business_id = uuid4()
    now = datetime.now(timezone.utc)
    for i in range(3):
        event = Event(
            id=uuid4(),
            business_id=business_id,
            event_type="inventory.changed",
            source="manual",
            source_id=f"inv-{i}",
            payload={"quantity_delta": i},
            checksum=f"c{i}",
            occurred_at=now - timedelta(minutes=i),
        )
        sqlite_session.add(event)
    await sqlite_session.commit()

    result = await what_changed(sqlite_session, business_id, since=now - timedelta(hours=1))
    assert result["summary"]["total"] == 3
    assert result["summary"]["event_type_counts"]["inventory.changed"] == 3


@pytest.mark.asyncio
async def test_why_causal_chain(sqlite_session: AsyncSession):
    business_id = uuid4()
    cause = Event(
        id=uuid4(),
        business_id=business_id,
        event_type="supplier.delivered",
        source="api",
        source_id="delivery-1",
        payload={},
        checksum="cc",
        occurred_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    effect = Event(
        id=uuid4(),
        business_id=business_id,
        event_type="inventory.changed",
        source="api",
        source_id="inv-1",
        payload={},
        checksum="ce",
        occurred_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    sqlite_session.add(cause)
    sqlite_session.add(effect)
    await sqlite_session.flush()

    await create_derivation(
        sqlite_session,
        business_id,
        cause.id,
        effect.id,
        derivation_type="caused_by",
        confidence=0.9,
    )
    await sqlite_session.commit()

    result = await why(sqlite_session, effect.id, business_id=business_id)
    assert len(result["derivations"]) == 1
    assert len(result["causal_chain"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# API integration tests (Postgres only)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_context_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    response = await client.post(
        f"/api/v1/intelligence/context?business_id={business_id}",
        json={
            "context_type": "holiday",
            "effective_from": datetime.now(timezone.utc).isoformat(),
            "payload": {"name": "Eid al-Fitr"},
        },
        headers=ctx["headers"],
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["context_type"] == "holiday"
    assert data["payload"]["name"] == "Eid al-Fitr"


@pytest.mark.asyncio
async def test_timeline_endpoint(authenticated_client: dict):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    await client.post(
        f"/api/v1/events?business_id={business_id}",
        json={
            "event_type": "sale.completed",
            "source": "manual",
            "source_id": "order-tl-1",
            "payload": {"total_amount": 50.0},
        },
        headers=ctx["headers"],
    )

    response = await client.get(
        f"/api/v1/intelligence/timeline?business_id={business_id}&limit=10",
        headers=ctx["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(e["event_type"] == "sale.completed" for e in data["items"])
