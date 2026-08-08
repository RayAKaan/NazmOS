"""Temporal Reasoning Engine service (Phase 3).

Answers time-based questions over the event stream and traces causal chains
via event derivations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventDerivation
from app.utils.logger import setup_logger

logger = setup_logger("temporal_reasoning")


def _to_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


async def get_timeline(
    session: AsyncSession,
    business_id: UUID | str,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Event], int]:
    """Return a paginated timeline of events for a business."""
    business_id = _to_uuid(business_id)
    query = select(Event).where(Event.business_id == business_id)
    count_query = select(func.count(Event.id)).where(Event.business_id == business_id)

    if from_date:
        query = query.where(Event.occurred_at >= from_date)
        count_query = count_query.where(Event.occurred_at >= from_date)
    if to_date:
        query = query.where(Event.occurred_at <= to_date)
        count_query = count_query.where(Event.occurred_at <= to_date)
    if event_type:
        query = query.where(Event.event_type == event_type)
        count_query = count_query.where(Event.event_type == event_type)

    query = query.order_by(Event.occurred_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    total_result = await session.execute(count_query)
    return list(result.scalars().all()), int(total_result.scalar_one())


async def what_changed(
    session: AsyncSession,
    business_id: UUID | str,
    since: datetime,
    limit: int = 100,
) -> dict[str, Any]:
    """Summarize what changed since a given timestamp."""
    business_id = _to_uuid(business_id)
    events, total = await get_timeline(
        session,
        business_id,
        from_date=since,
        limit=limit,
    )

    event_type_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for event in events:
        event_type_counts[event.event_type] = event_type_counts.get(event.event_type, 0) + 1
        source_counts[event.source] = source_counts.get(event.source, 0) + 1

    return {
        "since": since,
        "events": events,
        "summary": {
            "total": total,
            "event_type_counts": event_type_counts,
            "source_counts": source_counts,
        },
    }


async def create_derivation(
    session: AsyncSession,
    business_id: UUID | str,
    cause_event_id: UUID | str,
    effect_event_id: UUID | str,
    derivation_type: str = "caused_by",
    confidence: float = 0.5,
    evidence: dict[str, Any] | None = None,
) -> EventDerivation:
    """Record a causal or correlational link between two events."""
    business_id = _to_uuid(business_id)
    cause_event_id = _to_uuid(cause_event_id)
    effect_event_id = _to_uuid(effect_event_id)

    result = await session.execute(
        select(EventDerivation).where(
            EventDerivation.business_id == business_id,
            EventDerivation.cause_event_id == cause_event_id,
            EventDerivation.effect_event_id == effect_event_id,
            EventDerivation.derivation_type == derivation_type,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.confidence = confidence
        existing.evidence = evidence or existing.evidence
        await session.flush()
        return existing

    derivation = EventDerivation(
        business_id=business_id,
        cause_event_id=cause_event_id,
        effect_event_id=effect_event_id,
        derivation_type=derivation_type,
        confidence=confidence,
        evidence=evidence,
    )
    session.add(derivation)
    await session.flush()
    return derivation


async def why(
    session: AsyncSession,
    event_id: UUID | str,
    business_id: UUID | str | None = None,
    max_depth: int = 5,
) -> dict[str, Any]:
    """Return the causal chain leading to an event.

    Uses a recursive CTE to walk derivations backwards from the target event.
    """
    event_id = _to_uuid(event_id)
    params: dict[str, Any] = {"event_id": str(event_id), "max_depth": max_depth}
    business_filter = ""
    if business_id is not None:
        business_filter = "AND ed.business_id = :business_id"
        params["business_id"] = str(_to_uuid(business_id))

    sql = f"""
    WITH RECURSIVE causal_chain AS (
        SELECT
            ed.cause_event_id,
            ed.effect_event_id,
            ed.derivation_type,
            ed.confidence,
            ed.evidence,
            1 AS depth
        FROM event_derivations ed
        WHERE ed.effect_event_id = :event_id {business_filter}

        UNION ALL

        SELECT
            ed.cause_event_id,
            ed.effect_event_id,
            ed.derivation_type,
            ed.confidence,
            ed.evidence,
            cc.depth + 1
        FROM event_derivations ed
        JOIN causal_chain cc ON ed.effect_event_id = cc.cause_event_id
        WHERE cc.depth < :max_depth {business_filter}
    )
    SELECT DISTINCT cause_event_id FROM causal_chain
    """
    result = await session.execute(text(sql), params)
    cause_ids = {row[0] for row in result.fetchall()}

    if not cause_ids:
        # Return just the target event if no causal chain exists.
        target = await session.get(Event, event_id)
        return {
            "event_id": event_id,
            "causal_chain": [target] if target else [],
            "derivations": [],
        }

    cause_ids.add(str(event_id))
    events_result = await session.execute(
        select(Event).where(Event.id.in_(cause_ids)).order_by(Event.occurred_at)
    )
    events = list(events_result.scalars().all())
    event_map = {str(e.id): e for e in events}

    derivations_result = await session.execute(
        select(EventDerivation).where(
            EventDerivation.cause_event_id.in_(cause_ids),
            EventDerivation.effect_event_id.in_(cause_ids),
        )
    )
    derivations = list(derivations_result.scalars().all())

    # Build ordered chain from root cause to target event by walking derivations.
    ordered_chain = []
    target_event = event_map.get(str(event_id))
    if target_event:
        ordered_chain.append(target_event)
        current_id = str(event_id)
        for _ in range(max_depth):
            parent = next(
                (d for d in derivations if str(d.effect_event_id) == current_id),
                None,
            )
            if not parent:
                break
            parent_event = event_map.get(str(parent.cause_event_id))
            if parent_event:
                ordered_chain.append(parent_event)
                current_id = str(parent.cause_event_id)
            else:
                break
        ordered_chain.reverse()

    return {
        "event_id": event_id,
        "causal_chain": ordered_chain,
        "derivations": derivations,
    }
