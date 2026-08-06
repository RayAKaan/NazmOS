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
from app.middleware.rbac import require_role
from app.services.webhook_audit_service import (
    record_webhook_event,
    mark_webhook_processed,
    get_webhook_event,
)
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

    Returns the verified provider name ("foodics" | "salla" | "token_verified")
    and the raw request body. Raises 401 if verification fails.
    """
    raw_body = await request.body()

    if x_foodics_signature:
        secret = getattr(settings, "FOODICS_WEBHOOK_SECRET", "")
        if not secret:
            raise HTTPException(500, "FOODICS_WEBHOOK_SECRET not configured")
        expected = hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_foodics_signature):
            raise HTTPException(401, "Invalid Foodics webhook signature")
        return "foodics", raw_body

    if x_salla_signature:
        secret = getattr(settings, "SALLA_WEBHOOK_SECRET", "")
        if not secret:
            raise HTTPException(500, "SALLA_WEBHOOK_SECRET not configured")
        expected = hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_salla_signature):
            raise HTTPException(401, "Invalid Salla webhook signature")
        return "salla", raw_body

    if x_webhook_token:
        if getattr(settings, "ENVIRONMENT", "development") == "production":
            raise HTTPException(401, "Shared webhook tokens are disabled in production; use HMAC signatures")
        valid_tokens = [
            getattr(settings, "FOODICS_WEBHOOK_TOKEN", ""),
            getattr(settings, "SALLA_WEBHOOK_TOKEN", ""),
        ]
        if x_webhook_token not in valid_tokens:
            raise HTTPException(401, "Invalid webhook token")
        return "token_verified", raw_body

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
    _admin: None = Depends(require_role("admin", "owner")),
):
    """Replay a previously received webhook. Admin/owner only."""
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
