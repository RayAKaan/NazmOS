"""
WhatsApp Business Cloud – Webhook receiver
KSA – handles interactive Approve/Reject buttons from Nazm alerts and D2C orders
"""
import json
import logging
import os
import hmac
import hashlib
from uuid import UUID
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.whatsapp_bridge import send_notification
from app.services.agent_action_executor import approve_agent_action, reject_agent_action
from app.config import get_settings
from app.middleware.auth_middleware import get_current_user

logger = logging.getLogger("whatsapp_router")
router = APIRouter(prefix="/api/v1/whatsapp", tags=["WhatsApp"])

settings = get_settings()
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", settings.WHATSAPP_VERIFY_TOKEN)


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta WhatsApp webhook verification"""
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return int(hub_challenge) if hub_challenge and hub_challenge.isdigit() else hub_challenge
    raise HTTPException(403, "Verification failed")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive WhatsApp interactive button replies and inbound D2C text inquiries.
    If WHATSAPP_APP_SECRET is configured, verify Meta X-Hub-Signature-256 HMAC.
    """
    raw_body = await request.body()
    app_secret = getattr(settings, "WHATSAPP_APP_SECRET", "")
    if app_secret:
        signature = request.headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(401, "Invalid WhatsApp webhook signature")

    try:
        body = json.loads(raw_body.decode("utf-8") or "{}")
    except Exception:
        return {"status": "ok"}  # always 200 to Meta
    
    try:
        entry = body.get("entry", [{}])[0]
        change = entry.get("changes", [{}])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])
        
        for msg in messages:
            from_number = msg.get("from", "")
            
            # Interactive Button Replies (Approve / Reject)
            if msg.get("type") == "interactive":
                button_id = msg.get("interactive", {}).get("button_reply", {}).get("id", "")
                
                if button_id.startswith("approve_price_shield_"):
                    action_id = button_id.replace("approve_price_shield_", "")
                    result = await approve_agent_action(db, action_id, note="Approved Price Shield via WhatsApp interactive button")
                    outcome = result.get("outcome") or {}
                    await send_notification(
                        to_number=from_number,
                        text=f"✅ Price Shield Approved. {outcome.get('action', 'Action processed')} via NazmOS."
                    )
                elif button_id.startswith("approve_transfer_"):
                    action_id = button_id.replace("approve_transfer_", "")
                    result = await approve_agent_action(db, action_id, note="Approved transfer via WhatsApp interactive button")
                    await send_notification(
                        to_number=from_number,
                        text="✅ Transfer approved and recorded in NazmOS."
                    )
                elif button_id.startswith("approve_"):
                    action_id = button_id.replace("approve_", "")
                    result = await approve_agent_action(db, action_id, note="Approved via WhatsApp interactive button")
                    outcome = result.get("outcome") or {}
                    await send_notification(
                        to_number=from_number,
                        text=f"✅ Action Approved. {outcome.get('action', 'Action processed')} via NazmOS."
                    )
                elif button_id.startswith("reject_"):
                    action_id = button_id.replace("reject_", "")
                    await reject_agent_action(db, action_id, note="Rejected via WhatsApp interactive button")
                    await send_notification(
                        to_number=from_number,
                        text="❌ Action rejected. It has been dismissed from your NazmOS priority queue."
                    )
            
            # Text inquiries (D2C order routing / bot)
            elif msg.get("type") == "text":
                text_body = msg.get("text", {}).get("body", "").lower()
                logger.info(f"Received inbound text from {from_number}: {text_body}")
                if any(k in text_body for k in ["طلب", "order", "قهوة", "بكم", "سعر"]):
                    await send_notification(
                        to_number=from_number,
                        text="يا هلا بك! ☕ تم استلام استفسارك عبر نظام نظم (NazmOS). يمكنك إتمام الطلب والدفع مباشرة عبر رابط مدى/Apple Pay السريع: https://pay.nazmos.sa/checkout/demo"
                    )
    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}")
    
    return {"status": "ok"}


@router.post("/test-approve/{action_id}")
async def test_approve(
    action_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Test endpoint – simulates WhatsApp approve click – disabled in production."""
    if settings.ENVIRONMENT == "production":
        raise HTTPException(404, "Not found")
    try:
        result = await approve_agent_action(db, action_id, note="Simulated Test Approval")
    except Exception as exc:
        logger.warning(f"WhatsApp test approval could not run: {exc}")
        raise HTTPException(503, "WhatsApp approval simulation requires a reachable database")
    return {"ok": result.get("ok", False), "action_id": action_id, "simulated": "whatsapp_approve", "outcome": result.get("outcome")}
