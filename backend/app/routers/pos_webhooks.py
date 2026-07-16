"""
POS Webhook Router: Real-Time Order Sync for Foodics & Salla
HMAC signature verification enforced on all inbound webhooks.
"""
import hashlib
import hmac
from uuid import UUID
from fastapi import APIRouter, Request, Depends, HTTPException, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.adapters.foodics import handle_foodics_order_created
from app.adapters.salla import handle_salla_order_created
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/v1/pos", tags=["POS Real-Time Webhooks"])


async def verify_pos_webhook_auth(
    request: Request,
    x_foodics_signature: Optional[str] = Header(None),
    x_salla_signature: Optional[str] = Header(None),
    x_webhook_token: Optional[str] = Header(None),
) -> str:
    """Verify webhook authenticity via HMAC signature or shared token.

    Returns the verified provider name ("foodics" | "salla" | "token_verified").
    Raises 401 if verification fails.
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
        return "foodics"

    if x_salla_signature:
        secret = getattr(settings, "SALLA_WEBHOOK_SECRET", "")
        if not secret:
            raise HTTPException(500, "SALLA_WEBHOOK_SECRET not configured")
        expected = hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_salla_signature):
            raise HTTPException(401, "Invalid Salla webhook signature")
        return "salla"

    if x_webhook_token:
        if getattr(settings, "ENVIRONMENT", "development") == "production":
            raise HTTPException(401, "Shared webhook tokens are disabled in production; use HMAC signatures")
        valid_tokens = [
            getattr(settings, "FOODICS_WEBHOOK_TOKEN", ""),
            getattr(settings, "SALLA_WEBHOOK_TOKEN", ""),
        ]
        if x_webhook_token not in valid_tokens:
            raise HTTPException(401, "Invalid webhook token")
        return "token_verified"

    raise HTTPException(401, "Missing webhook authentication")


@router.post("/foodics/webhook")
async def receive_foodics_webhook(
    business_id: UUID = Query(...),
    request: Request = None,
    _provider: str = Depends(verify_pos_webhook_auth),
    db: AsyncSession = Depends(get_db),
):
    """Receives live order created webhooks from Foodics POS"""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    res = await handle_foodics_order_created(payload, business_id, db)
    return res


@router.post("/salla/webhook")
async def receive_salla_webhook(
    business_id: UUID = Query(...),
    request: Request = None,
    _provider: str = Depends(verify_pos_webhook_auth),
    db: AsyncSession = Depends(get_db),
):
    """Receives live order created webhooks from Salla E-Commerce"""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    res = await handle_salla_order_created(payload, business_id, db)
    return res
