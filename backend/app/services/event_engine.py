"""Universal Event Engine service.

Handles event validation, deduplication, persistence, and publication.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import Event, EventType, EventSubscription
from app.services.context_engine import build_context_snapshot
from app.schemas.events import (
    BUILTIN_EVENT_SCHEMAS,
    EventIngest,
    EventTypeCreate,
    EventSubscriptionCreate,
)
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger("event_engine")


def _canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON serialization for checksum computation."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _compute_checksum(event_data: dict[str, Any]) -> str:
    """Compute SHA-256 checksum over a canonical representation of the event."""
    canonical = _canonical_json(event_data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a payload against a built-in schema if one exists."""
    model = BUILTIN_EVENT_SCHEMAS.get(event_type)
    if model is None:
        return payload
    validated = model.model_validate(payload)
    return validated.model_dump(mode="json", exclude_unset=False)


async def _get_or_create_event_type(
    session: AsyncSession,
    name: str,
    version: int = 1,
) -> EventType:
    """Return existing event type or create a generic placeholder."""
    result = await session.execute(
        select(EventType).where(EventType.name == name, EventType.version == version)
    )
    event_type = result.scalar_one_or_none()
    if event_type is None:
        event_type = EventType(
            name=name,
            version=version,
            description=f"Auto-registered event type: {name}",
            schema={},
            is_system=False,
        )
        session.add(event_type)
        await session.flush()
    return event_type


async def ingest_event(
    session: AsyncSession,
    business_id: UUID | str,
    event: EventIngest,
) -> Event:
    """Persist a single event and dispatch it for processing.

    If Celery is enabled, the event is queued asynchronously. Otherwise it is
    processed synchronously so the backend works in zero-cost (no Redis) mode.
    """
    validated_payload = _validate_payload(event.event_type, event.payload)

    # Phase 3: enrich the event with active external context unless the caller
    # already supplied a context snapshot (e.g. replay or manual override).
    context_snapshot = event.context_snapshot
    if context_snapshot is None:
        try:
            context_snapshot = await build_context_snapshot(session, business_id, at=event.occurred_at)
        except Exception as exc:
            logger.warning(
                "Failed to build context snapshot; continuing without context",
                extra={"business_id": str(business_id), "error": str(exc)},
            )
            context_snapshot = {}

    checksum_data = {
        "event_type": event.event_type,
        "version": 1,
        "source": event.source,
        "source_id": event.source_id,
        "payload": validated_payload,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
    }
    checksum = _compute_checksum(checksum_data)

    await _get_or_create_event_type(session, event.event_type)

    event_record = Event(
        business_id=business_id,
        event_type=event.event_type,
        version=1,
        source=event.source,
        source_id=event.source_id,
        payload=validated_payload,
        context_snapshot=context_snapshot,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        checksum=checksum,
        occurred_at=event.occurred_at or datetime.now(timezone.utc),
        processed=False,
    )
    session.add(event_record)
    await session.commit()
    await session.refresh(event_record)

    logger.info(
        "Event ingested",
        extra={
            "event_id": str(event_record.id),
            "business_id": str(business_id),
            "event_type": event.event_type,
            "source": event.source,
        },
    )

    if settings.USE_CELERY:
        from app.tasks.event_tasks import process_event
        process_event.delay(str(event_record.id))
    else:
        from app.services.event_processor import process_event_sync
        await process_event_sync(session, event_record)

    return event_record


async def ingest_events(
    session: AsyncSession,
    business_id: UUID | str,
    events: list[EventIngest],
) -> list[Event]:
    """Persist a batch of events."""
    records = []
    for event in events:
        record = await ingest_event(session, business_id, event)
        records.append(record)
    return records


async def create_event_type(
    session: AsyncSession,
    data: EventTypeCreate,
) -> EventType:
    """Register a new event type in the registry."""
    event_type = EventType(
        name=data.name,
        version=data.version,
        description=data.description,
        schema=data.json_schema,
        example=data.example,
        is_system=False,
    )
    session.add(event_type)
    await session.commit()
    await session.refresh(event_type)
    return event_type


async def create_event_subscription(
    session: AsyncSession,
    business_id: UUID | str | None,
    data: EventSubscriptionCreate,
) -> EventSubscription:
    """Register a consumer subscription."""
    subscription = EventSubscription(
        business_id=business_id,
        consumer_name=data.consumer_name,
        event_pattern=data.event_pattern,
        queue_or_channel=data.queue_or_channel,
        is_active=data.is_active,
    )
    session.add(subscription)
    await session.commit()
    await session.refresh(subscription)
    return subscription


async def list_event_subscriptions(
    session: AsyncSession,
    business_id: UUID | str | None = None,
) -> list[EventSubscription]:
    """Return active subscriptions, optionally scoped to a business."""
    query = select(EventSubscription).where(EventSubscription.is_active == True)
    if business_id is not None:
        query = query.where(
            (EventSubscription.business_id == business_id) | (EventSubscription.business_id.is_(None))
        )
    result = await session.execute(query)
    return list(result.scalars().all())


async def publish_event_to_bus(
    event_record: Event,
    subscriptions: list[EventSubscription] | None = None,
) -> None:
    """Publish a processed event to the Redis Pub/Sub bus if Redis is enabled."""
    if not settings.USE_REDIS or not settings.REDIS_URL:
        return

    try:
        import redis.asyncio as aioredis
    except ImportError:  # pragma: no cover
        logger.warning("redis.asyncio not available; skipping event bus publish")
        return

    client = aioredis.from_url(settings.REDIS_URL)
    try:
        message = json.dumps(
            {
                "event_id": str(event_record.id),
                "business_id": str(event_record.business_id),
                "event_type": event_record.event_type,
                "source": event_record.source,
                "payload": event_record.payload,
                "occurred_at": event_record.occurred_at.isoformat(),
            },
            default=str,
        )
        channel = f"nazmos:events:{event_record.business_id}"
        await client.publish(channel, message)

        if subscriptions:
            for sub in subscriptions:
                if _pattern_matches(sub.event_pattern, event_record.event_type):
                    await client.publish(sub.queue_or_channel, message)
    except Exception as exc:
        logger.warning("Failed to publish event to Redis bus", extra={"error": str(exc)})
    finally:
        await client.aclose()


def _pattern_matches(pattern: str, event_type: str) -> bool:
    """Simple glob matcher for event patterns (* and ?)."""
    import fnmatch
    return fnmatch.fnmatch(event_type, pattern)
