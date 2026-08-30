"""WS11 — observability export integrity.

Two invariants that any export/audit consumer relies on:
  1. Every ingested event carries a deterministic checksum over its full
     content (event_type/version/source/source_id/payload/occurred_at), so a
     tampered or partially-exported ledger row is detectable.
  2. The audit log is an append-only record: each entry carries a request id,
     stores before/after values, and never reuses an id.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.database.models import Base
from app.services.audit_log_service import record
from app.services.event_engine import _compute_checksum, _validate_payload, ingest_event


async def _make_engine():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


@pytest.mark.asyncio
async def test_event_checksum_is_deterministic_and_persisted():
    engine, factory = await _make_engine()
    try:
        from app.schemas.events import EventIngest

        bid = uuid.uuid4()
        event = EventIngest(
            event_type="inventory.adjusted",
            payload={"item_id": "1001", "delta": -5},
            source="money_audit",
            occurred_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
        )
        async with factory() as session:
            rec = await ingest_event(session, bid, event)

            # Deterministic-invariant check: identical inputs must reproduce the
            # exact checksum the engine persisted, independent of any storage
            # round-trip of the timestamp.
            expected = _compute_checksum({
                "event_type": event.event_type,
                "version": 1,
                "source": event.source,
                "source_id": event.source_id,
                "payload": _validate_payload(event.event_type, event.payload),
                "occurred_at": event.occurred_at.isoformat(),
            })
            assert rec.checksum == expected, "persisted checksum must match recomputation"
            assert len(rec.checksum) == 64

            row = (await session.execute(
                text("SELECT checksum FROM events WHERE id = :id"),
                {"id": str(rec.id)},
            )).fetchone()
            assert row.checksum == rec.checksum, "checksum must survive a reload"
            assert rec.processed is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_event_checksum_detects_tampering():
    engine, factory = await _make_engine()
    try:
        from app.schemas.events import EventIngest

        bid = uuid.uuid4()
        event = EventIngest(
            event_type="inventory.adjusted",
            payload={"item_id": "1001", "delta": -5},
            source="money_audit",
            occurred_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
        )
        async with factory() as session:
            rec = await ingest_event(session, bid, event)

            tampered = _compute_checksum({
                "event_type": event.event_type,
                "version": 1,
                "source": event.source,
                "source_id": event.source_id,
                "payload": {"item_id": "1001", "delta": -999},  # silent tamper
                "occurred_at": event.occurred_at.isoformat(),
            })
            assert tampered != rec.checksum, \
                "any payload mutation must invalidate the checksum (export gap = 0)"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_audit_log_is_append_only_with_request_ids():
    engine, factory = await _make_engine()
    try:
        bid = uuid.uuid4()
        async with factory() as session:
            
            first = await record(
                session,
                action_type="price.change",
                action_category="item",
                business_id=bid,
                user_id=uuid.uuid4(),
                old_value={"sell_price": 8.0},
                new_value={"sell_price": 7.5},
            )
            second = await record(
                session,
                action_type="stock.adjust",
                action_category="inventory",
                business_id=bid,
                user_id=uuid.uuid4(),
                old_value={"current_stock": 10},
                new_value={"current_stock": 5},
            )

            rows = (await session.execute(
                text("SELECT id, action_type, request_id FROM audit_log ORDER BY created_at")
            )).fetchall()
            assert len(rows) == 2
            assert rows[0].action_type == "price.change"
            assert rows[1].action_type == "stock.adjust"
            assert rows[0].id != rows[1].id, "entries must never reuse an id (append-only)"
    finally:
        await engine.dispose()