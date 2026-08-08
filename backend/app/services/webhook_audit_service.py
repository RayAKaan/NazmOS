"""Webhook audit service.

Records every inbound webhook, detects duplicates, and supports replay.
"""
from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WebhookEvent


def _compute_payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


async def record_webhook_event(
    session: AsyncSession,
    business_id: UUID | str,
    provider: str,
    payload: bytes,
    signature_valid: bool,
    event_type: str | None = None,
    external_event_id: str | None = None,
    status: str = "received",
    error: str | None = None,
) -> WebhookEvent:
    """Persist a webhook event. Returns the existing event if duplicate."""
    if external_event_id:
        result = await session.execute(
            select(WebhookEvent).where(
                WebhookEvent.provider == provider,
                WebhookEvent.external_event_id == external_event_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    try:
        payload_json = __import__("json").loads(payload.decode("utf-8"))
    except Exception:
        payload_json = {"raw_base64": payload.decode("latin-1", errors="replace")}

    event = WebhookEvent(
        business_id=business_id,
        provider=provider,
        event_type=event_type,
        external_event_id=external_event_id,
        signature_valid=signature_valid,
        payload_hash=_compute_payload_hash(payload),
        payload=payload_json,
        status=status,
        error=error,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def mark_webhook_processed(
    session: AsyncSession,
    event_id: UUID | str,
    status: str = "processed",
    error: str | None = None,
) -> None:
    from datetime import datetime, timezone
    event = await session.get(WebhookEvent, event_id)
    if event:
        event.status = status
        event.error = error
        event.processed_at = datetime.now(timezone.utc)
        await session.commit()


async def get_webhook_event(session: AsyncSession, event_id: UUID | str) -> WebhookEvent | None:
    return await session.get(WebhookEvent, event_id)
