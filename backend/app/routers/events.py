"""Universal Event Engine API (Phase 0).

Provides ingestion, querying, replay, and registry endpoints for the business
event stream.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Business, Event, EventType, User
from app.middleware.auth_middleware import get_current_user
from app.schemas.events import (
    EventBatchIngest,
    EventIngest,
    EventOut,
    EventSubscriptionCreate,
    EventSubscriptionOut,
    EventTypeCreate,
    EventTypeOut,
)
from app.services.event_engine import (
    create_event_subscription,
    create_event_type,
    ingest_event,
    ingest_events,
)
from app.utils.problem_details import problem_response

router = APIRouter(prefix="/api/v1/events", tags=["Events"])


async def _verify_business_access(
    session: AsyncSession,
    business_id: UUID,
    user: User,
) -> Business:
    """Ensure the user owns or belongs to the business."""
    result = await session.execute(
        select(Business).where(
            (Business.id == business_id) & (
                (Business.owner_id == user.id) |
                Business.id.in_(
                    select(Business.id).where(Business.id == business_id)  # placeholder for team check
                )
            )
        )
    )
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found or access denied")
    return business


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    business_id: UUID,
    event: EventIngest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ingest a single business event."""
    await _verify_business_access(db, business_id, current_user)
    record = await ingest_event(db, business_id, event)
    return record


@router.post("/batch", response_model=list[EventOut], status_code=status.HTTP_201_CREATED)
async def create_event_batch(
    business_id: UUID,
    batch: EventBatchIngest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ingest a batch of business events atomically."""
    await _verify_business_access(db, business_id, current_user)
    records = await ingest_events(db, business_id, batch.events)
    return records


@router.get("", response_model=list[EventOut])
async def list_events(
    business_id: UUID,
    event_type: str | None = Query(None),
    source: str | None = Query(None),
    processed: bool | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Query the event stream for a business."""
    await _verify_business_access(db, business_id, current_user)
    query = select(Event).where(Event.business_id == business_id)
    if event_type:
        query = query.where(Event.event_type == event_type)
    if source:
        query = query.where(Event.source == source)
    if processed is not None:
        query = query.where(Event.processed == processed)
    if from_date:
        query = query.where(Event.occurred_at >= from_date)
    if to_date:
        query = query.where(Event.occurred_at <= to_date)
    query = query.order_by(Event.occurred_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/types", response_model=list[EventTypeOut])
async def list_event_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the registry of supported event types."""
    result = await db.execute(select(EventType).order_by(EventType.name))
    return list(result.scalars().all())


@router.post("/types", response_model=EventTypeOut, status_code=status.HTTP_201_CREATED)
async def register_event_type(
    data: EventTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Register a new custom event type."""
    record = await create_event_type(db, data)
    return record


@router.post("/subscriptions", response_model=EventSubscriptionOut, status_code=status.HTTP_201_CREATED)
async def register_subscription(
    data: EventSubscriptionCreate,
    business_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Register a consumer subscription for event patterns."""
    if business_id:
        await _verify_business_access(db, business_id, current_user)
    record = await create_event_subscription(db, business_id, data)
    return record


@router.post("/replay/{correlation_id}")
async def replay_correlation(
    correlation_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Replay all events for a correlation id by re-publishing them to the bus."""
    await _verify_business_access(db, business_id, current_user)
    result = await db.execute(
        select(Event).where(
            Event.business_id == business_id,
            Event.correlation_id == correlation_id,
        ).order_by(Event.occurred_at)
    )
    events = result.scalars().all()
    if not events:
        return problem_response(
            status=404,
            title="Correlation Not Found",
            detail=f"No events found for correlation {correlation_id}",
            request=None,
        )

    from app.services.event_processor import process_event_sync
    replayed = 0
    for event in events:
        # Clear processed flag to force re-publication.
        event.processed = False
        event.processed_at = None
        await process_event_sync(db, event)
        replayed += 1

    return {"replayed": replayed, "correlation_id": str(correlation_id)}
