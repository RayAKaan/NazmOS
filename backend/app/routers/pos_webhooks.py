"""
POS Webhook Router: Real-Time Order Sync for Foodics & Salla
HMAC signature verification enforced on all inbound webhooks.
"""
import hashlib
import hmac
import json
from uuid import UUID
from fastapi import APIRouter, Request, Depends, HTTPException, Query, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database import get_db
from app.database.models import Business, WebhookEvent
from app.adapters.foodics import handle_foodics_order_created
from app.adapters.salla import handle_salla_order_created
from app.config import get_settings
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_platform_operator
from app.services.webhook_audit_service import (
    record_webhook_event,
    mark_webhook_processed,
    get_webhook_event,
)
from app.services.event_engine import ingest_event
from app.schemas.events import EventIngest
from app.utils.problem_details import problem_response

settings = get_settings()
router = APIRouter(prefix="/api/v1/pos", tags=["POS Real-Time Webhooks"])


async def verify_pos_webhook_auth(
    request: Request,
    x_foodics_signature: Optional[str] = Header(None),
    x_salla_signature: Optional[str] = Header(None),
    x_webhook_token: Optional[str] = Header(None),
) -> tuple[str, bytes]:
    """Verify webhook authenticity via HMAC signature or shared token.

    Returns the verified provider name ("foodics" | "salla") and the raw
    request body. Raises 401 if verification fails.
    """
    raw_body = await request.body()

    if x_foodics_signature:
        secret = getattr(settings, "FOODICS_WEBHOOK_SECRET", "")
        if not secret:
            raise HTTPException(401, "FOODICS_WEBHOOK_SECRET not configured; cannot verify signature")
        expected = hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_foodics_signature):
            raise HTTPException(401, "Invalid Foodics webhook signature")
        return "foodics", raw_body

    if x_salla_signature:
        secret = getattr(settings, "SALLA_WEBHOOK_SECRET", "")
        if not secret:
            raise HTTPException(401, "SALLA_WEBHOOK_SECRET not configured; cannot verify signature")
        expected = hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_salla_signature):
            raise HTTPException(401, "Invalid Salla webhook signature")
        return "salla", raw_body

    if x_webhook_token:
        if getattr(settings, "ENVIRONMENT", "development") == "production":
            raise HTTPException(401, "Shared webhook tokens are disabled in production; use HMAC signatures")
        if hmac.compare_digest(x_webhook_token, getattr(settings, "FOODICS_WEBHOOK_TOKEN", "")):
            return "foodics", raw_body
        if hmac.compare_digest(x_webhook_token, getattr(settings, "SALLA_WEBHOOK_TOKEN", "")):
            return "salla", raw_body
        raise HTTPException(401, "Invalid webhook token")

    raise HTTPException(401, "Missing webhook authentication")


def _extract_external_event_id(provider: str, payload: dict) -> Optional[str]:
    if provider == "foodics":
        return payload.get("order", {}).get("id") or payload.get("id")
    if provider == "salla":
        return payload.get("data", {}).get("id") or payload.get("id")
    return None


def _extract_event_type(provider: str, payload: dict) -> Optional[str]:
    if provider == "foodics":
        return payload.get("event")
    if provider == "salla":
        return payload.get("event")
    return None


async def _process_webhook(
    provider: str,
    payload: dict,
    business_id: UUID,
    db: AsyncSession,
) -> dict:
    if provider == "foodics":
        return await handle_foodics_order_created(payload, business_id, db)
    if provider == "salla":
        return await handle_salla_order_created(payload, business_id, db)
    raise HTTPException(400, f"Unsupported webhook provider: {provider}")


async def _emit_pos_event(
    db: AsyncSession,
    business_id: UUID,
    provider: str,
    webhook_event: WebhookEvent,
    payload: dict,
) -> None:
    """Emit a normalized event into the Universal Event Engine.

    Legacy adapter handlers continue to write to transactions/inventory tables
    for backward compatibility. The normalized event becomes the source of truth
    for future intelligence features.
    """
    external_event_id = webhook_event.external_event_id or str(webhook_event.id)
    event = EventIngest(
        event_type="pos.order.received",
        source=provider,
        source_id=external_event_id,
        payload={
            "provider": provider,
            "external_event_id": external_event_id,
            "provider_event_type": webhook_event.event_type,
            "payload_summary": _summarize_payload(provider, payload),
        },
        actor_type="webhook",
        correlation_id=webhook_event.id,
    )
    await ingest_event(db, business_id, event)


def _summarize_payload(provider: str, payload: dict) -> dict:
    """Extract a small, safe summary of a POS webhook payload for the event stream."""
    summary: dict = {"provider": provider}
    if provider == "foodics":
        order = payload.get("order", {}) or {}
        summary["order_id"] = order.get("id")
        summary["status"] = order.get("status")
        summary["total"] = order.get("total")
    elif provider == "salla":
        data = payload.get("data", {}) or {}
        summary["order_id"] = data.get("id")
        summary["status"] = data.get("status")
        summary["total"] = data.get("total")
    return summary


@router.post("/foodics/webhook")
async def receive_foodics_webhook(
    business_id: UUID = Query(...),
    request: Request = None,
    verified: tuple[str, bytes] = Depends(verify_pos_webhook_auth),
    db: AsyncSession = Depends(get_db),
):
    """Receives live order created webhooks from Foodics POS"""
    provider, raw_body = verified
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        payload = {}

    event = await record_webhook_event(
        session=db,
        business_id=business_id,
        provider=provider,
        payload=raw_body,
        signature_valid=True,
        event_type=_extract_event_type(provider, payload),
        external_event_id=_extract_external_event_id(provider, payload),
    )

    # Idempotency: return 200 immediately if this event was already processed.
    if event.status == "processed":
        return {"status": "already_processed", "event_id": str(event.id)}

    try:
        result = await _process_webhook(provider, payload, business_id, db)
        await _emit_pos_event(db, business_id, provider, event, payload)
        await mark_webhook_processed(db, event.id, status="processed")
        return result
    except Exception as exc:
        await mark_webhook_processed(db, event.id, status="failed", error=str(exc))
        raise


@router.post("/salla/webhook")
async def receive_salla_webhook(
    business_id: UUID = Query(...),
    request: Request = None,
    verified: tuple[str, bytes] = Depends(verify_pos_webhook_auth),
    db: AsyncSession = Depends(get_db),
):
    """Receives live order created webhooks from Salla E-Commerce"""
    provider, raw_body = verified
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        payload = {}

    event = await record_webhook_event(
        session=db,
        business_id=business_id,
        provider=provider,
        payload=raw_body,
        signature_valid=True,
        event_type=_extract_event_type(provider, payload),
        external_event_id=_extract_external_event_id(provider, payload),
    )

    if event.status == "processed":
        return {"status": "already_processed", "event_id": str(event.id)}

    try:
        result = await _process_webhook(provider, payload, business_id, db)
        await _emit_pos_event(db, business_id, provider, event, payload)
        await mark_webhook_processed(db, event.id, status="processed")
        return result
    except Exception as exc:
        await mark_webhook_processed(db, event.id, status="failed", error=str(exc))
        raise


@router.post("/admin/webhooks/{event_id}/replay")
async def replay_webhook(
    request: Request,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Replay a previously received webhook. Platform operator only.

    Previously gated by ``require_role("admin", "owner")``, which let any
    business owner replay another tenant's webhook events (cross-tenant IDOR).
    """
    await assert_platform_operator(db, current_user)
    event = await get_webhook_event(db, event_id)
    if not event:
        return problem_response(
            status=404,
            title="Webhook Event Not Found",
            detail=f"No webhook event found with id {event_id}",
            request=request,
        )

    try:
        result = await _process_webhook(event.provider, event.payload, event.business_id, db)
        await mark_webhook_processed(db, event.id, status="processed")
        return {"status": "replayed", "event_id": str(event.id), "result": result}
    except Exception as exc:
        await mark_webhook_processed(db, event.id, status="failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Replay failed: {exc}",
        )
