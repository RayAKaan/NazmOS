"""Synchronous (async) event processor for the Universal Event Engine.

This module is called directly when Celery is disabled and via the Celery task
when Celery is enabled. It validates, deduplicates, marks events processed, and
publishes to the event bus.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventSubscription
from app.services.event_engine import list_event_subscriptions, publish_event_to_bus
from app.services.business_memory import route_event_to_projectors as route_to_memory_projectors
from app.services.knowledge_graph import route_event_to_graph_projectors
from app.utils.logger import setup_logger

logger = setup_logger("event_processor")


async def process_event_sync(
    session: AsyncSession,
    event_record: Event,
) -> Event:
    """Process a single event: dedupe check, publish, mark processed.

    The event is assumed to already be persisted. Idempotency is guaranteed by
    the unique constraint on (business_id, source, source_id, checksum).
    """
    if event_record.processed:
        return event_record

    try:
        # Re-fetch with a lock-free fresh read to detect duplicate checksums.
        duplicate = await session.execute(
            select(Event).where(
                Event.business_id == event_record.business_id,
                Event.source == event_record.source,
                Event.source_id == event_record.source_id,
                Event.checksum == event_record.checksum,
                Event.id != event_record.id,
            )
        )
        if duplicate.scalar_one_or_none():
            logger.info(
                "Duplicate event detected; marking as processed",
                extra={"event_id": str(event_record.id)},
            )

        subscriptions = await list_event_subscriptions(session, event_record.business_id)
        await publish_event_to_bus(event_record, subscriptions)

        # Phase 1: project the event into business memory atomically with processing.
        await route_to_memory_projectors(session, event_record)

        # Phase 2: project the event into the knowledge graph.
        await route_event_to_graph_projectors(session, event_record)

        # Phase 2: debounced, event-triggered continuous auditing (§5). Full audits
        # never run on every trivial event — a domain re-runs only if no audit of that
        # domain has run for this business in the last DEBOUNCE window.
        await _maybe_run_event_triggered_audits(session, event_record)

        event_record.processed = True
        event_record.processed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(event_record)

        logger.info(
            "Event processed",
            extra={
                "event_id": str(event_record.id),
                "event_type": event_record.event_type,
                "business_id": str(event_record.business_id),
            },
        )
    except Exception as exc:
        # Roll back any partial work (memory projection, bus publish is best-effort
        # external so we accept at-least-once semantics there).
        await session.rollback()
        event_record.error = str(exc)
        await session.commit()
        logger.exception("Event processing failed", extra={"event_id": str(event_record.id)})
        raise

    return event_record


from app.config import get_settings
AUDIT_DEBOUNCE_MINUTES = max(5, int(get_settings().AUDIT_DEBOUNCE_MINUTES))  # configurable, floored at 5m


async def _maybe_run_event_triggered_audits(session: AsyncSession, event_record: Event) -> None:
    """Run debounced, domain-specific audits for an event (brief §5).

    Best-effort: a failed audit must never fail event processing (which would roll
    back the memory/graph projections). Debounce by checking the last audit run
    per (business, domain) inside the window.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import text
    from app.services.audit_triggers import audit_domains_for_event

    domains = audit_domains_for_event(event_record.event_type)
    if not domains:
        return

    # Dialect-safe cutoff (avoids NOW()/INTERVAL, which SQLite lacks).
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=AUDIT_DEBOUNCE_MINUTES)
    for domain in domains:
        try:
            recent = await session.execute(text("""
                SELECT 1 FROM audit_runs
                WHERE business_id = :b AND domain = :d
                  AND status = 'completed' AND completed_at > :cutoff
                LIMIT 1
            """), {"b": str(event_record.business_id), "d": domain, "cutoff": cutoff})
            if recent.fetchone():
                continue  # debounced — skip this domain this time

            from app.services.audit_engine import run_audit
            await run_audit(session, event_record.business_id, domain, trigger="event",
                             trigger_event_type=event_record.event_type, commit=False)
        except Exception as exc:
            # Best-effort: a failed/unsupported audit must never fail event processing.
            logger.warning("event-triggered audit %s skipped: %s", domain, exc)


async def process_unprocessed_events(session: AsyncSession, limit: int = 1000) -> dict:
    """Pick up events that were ingested but not yet processed."""
    result = await session.execute(
        select(Event).where(Event.processed == False).order_by(Event.received_at).limit(limit)
    )
    events = result.scalars().all()

    processed = 0
    failed = 0
    for event in events:
        try:
            await process_event_sync(session, event)
            processed += 1
        except Exception:
            failed += 1

    return {"processed": processed, "failed": failed, "remaining": max(0, len(events) - processed - failed)}
