"""Celery tasks for the Business Memory Engine (Phase 1).
"""
from __future__ import annotations

from app.config import get_settings
from app.database.connection import AsyncSessionLocal
from app.database.models import Event
from app.services.business_memory import route_event_to_projectors
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger("celery.business_memory")


async def _update_business_memory(event_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        event = await session.get(Event, event_id)
        if not event:
            logger.warning("Event not found for memory projection", extra={"event_id": event_id})
            return {"status": "not_found", "event_id": event_id}
        await route_event_to_projectors(session, event)
        await session.commit()
        return {"status": "projected", "event_id": event_id, "event_type": event.event_type}


if settings.USE_CELERY:
    from app.celery_app import celery_app

    @celery_app.task(name="app.tasks.business_memory_tasks.update_business_memory")
    def update_business_memory(event_id: str) -> dict:
        import asyncio
        return asyncio.run(_update_business_memory(event_id))

    @celery_app.task(name="app.tasks.business_memory_tasks.rebuild_business_memory")
    def rebuild_business_memory(business_id: str) -> dict:
        """Rebuild all business memory for a tenant by replaying its event stream."""
        import asyncio
        from sqlalchemy import select
        from app.database.models import BusinessMemory, MemoryUpdate
        from app.services.business_memory import replay_events_to_memory

        async def _run() -> dict:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Event).where(Event.business_id == business_id).order_by(Event.occurred_at)
                )
                events = list(result.scalars().all())
                await replay_events_to_memory(session, business_id, events)
                memory_count = await session.scalar(
                    select(BusinessMemory.id).where(BusinessMemory.business_id == business_id).count()
                )
                update_count = await session.scalar(
                    select(MemoryUpdate.id).where(MemoryUpdate.business_id == business_id).count()
                )
                return {
                    "status": "rebuilt",
                    "business_id": business_id,
                    "events_replayed": len(events),
                    "memory_documents": memory_count,
                    "memory_updates": update_count,
                }

        return asyncio.run(_run())
