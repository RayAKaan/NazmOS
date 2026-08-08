"""Celery tasks for the Universal Event Engine."""
from __future__ import annotations

from app.config import get_settings
from app.database.connection import AsyncSessionLocal
from app.database.models import Event
from app.services.event_processor import process_event_sync, process_unprocessed_events
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger("celery.events")


async def _process_event(event_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        event = await session.get(Event, event_id)
        if not event:
            return {"status": "not_found", "event_id": event_id}
        await process_event_sync(session, event)
        return {"status": "processed", "event_id": event_id}


if settings.USE_CELERY:
    from app.celery_app import celery_app

    @celery_app.task(name="app.tasks.event_tasks.process_event")
    def process_event(event_id: str) -> dict:
        import asyncio
        return asyncio.run(_process_event(event_id))

    @celery_app.task(name="app.tasks.event_tasks.process_unprocessed_events")
    def process_unprocessed_events_task(limit: int = 1000) -> dict:
        import asyncio

        async def _run() -> dict:
            async with AsyncSessionLocal() as session:
                return await process_unprocessed_events(session, limit=limit)

        return asyncio.run(_run())
