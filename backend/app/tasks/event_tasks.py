"""Celery tasks for the Universal Event Engine."""
from __future__ import annotations

from app.config import get_settings
from app.database.connection import get_sync_session, _get_sync_engine
from app.database.models import Event
from app.utils.logger import setup_logger
from sqlalchemy import select

settings = get_settings()
logger = setup_logger("celery.events")

if settings.USE_CELERY:
    from app.celery_app import celery_app

    @celery_app.task(name="app.tasks.event_tasks.process_event")
    def process_event(event_id: str) -> dict:
        from sqlalchemy.orm import Session
        engine = _get_sync_engine()
        with Session(engine) as session:
            event = session.get(Event, event_id)
            if not event:
                return {"status": "not_found", "event_id": event_id}
            if event.processed:
                return {"status": "already_processed", "event_id": event_id}
            event.processed = True
            from datetime import datetime, timezone
            event.processed_at = datetime.now(timezone.utc)
            session.commit()
            return {"status": "processed", "event_id": event_id}

    @celery_app.task(name="app.tasks.event_tasks.process_unprocessed_events")
    def process_unprocessed_events_task(limit: int = 1000) -> dict:
        from sqlalchemy.orm import Session
        engine = _get_sync_engine()
        with Session(engine) as session:
            result = session.execute(
                select(Event).where(Event.processed == False).order_by(Event.received_at).limit(limit)
            )
            events = result.scalars().all()
            processed = 0
            failed = 0
            from datetime import datetime, timezone
            for event in events:
                try:
                    event.processed = True
                    event.processed_at = datetime.now(timezone.utc)
                    session.commit()
                    processed += 1
                except Exception:
                    session.rollback()
                    failed += 1
            return {"processed": processed, "failed": failed, "remaining": max(0, len(events) - processed - failed)}
