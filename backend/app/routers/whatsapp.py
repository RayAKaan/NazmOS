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
from app.database.connection import clear_rls_tenant_id, set_rls_tenant_id
from app.services.whatsapp_bridge import send_notification
from app.orchestration.runner import run_agent_approval, run_agent_rejection
from app.config import get_settings
from app.middleware.auth_middleware import get_current_user

logger = logging.getLogger("whatsapp_router")
router = APIRouter(prefix="/api/v1/whatsapp", tags=["WhatsApp"])

settings = get_settings()
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", settings.WHATSAPP_VERIFY_TOKEN)


def _parse_button_target(button_id: str) -> tuple[UUID | None, UUID | None]:
    """Extract (business_id, action_id) from a reply-button id.

    Button ids are formed ``{prefix}_{business_id}_{action_id}`` (see
    ``services.whatsapp_bridge.send_approval_request``).  The webhook is
    unauthenticated, so the tenant CANNOT be read from the database first
    (Postgres RLS hides every row until a tenant context is set); it must be
    carried in the button id itself and validated here.  Returns (None, None)
    for ids that do not carry both UUIDs (legacy buttons / tampering).
    """
    if not button_id:
        return None, None
    action_part, sep, action_id = button_id.rpartition("_")
    if not sep or not action_id:
        return None, None
    business_part, sep2, business_id = action_part.rpartition("_")
    if not sep2 or not business_id:
        return None, None
    try:
        bid = UUID(business_id)
    except (ValueError, AttributeError):
        return None, None
    try:
        aid = UUID(action_id)
    except (ValueError, AttributeError):
        return None, None
    return bid, aid


async def _run_tenant_scoped(db: AsyncSession, business_id: UUID, action) -> dict:
    """Run an agent decision with its request session scoped to ``business_id``.

    The dependency-opened transaction predates tenant resolution (RLS hides
    rows until a tenant is set), so we commit it first to force the engine
    begin-listener to re-apply ``SET LOCAL app.current_tenant_id`` + the app
    role on the next transaction.  The tenant ContextVar is torn down in
    ``finally``; the operation itself also carries ``business_id`` in its WHERE
    clause (record.py) as defense-in-depth.
    """
    token = set_rls_tenant_id(str(business_id))
    try:
        await db.commit()
        return await action()
    finally:
        clear_rls_tenant_id()


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

    Meta X-Hub-Signature-256 HMAC is always enforced. When WHATSAPP_APP_SECRET
    is not configured the endpoint fails closed (401/503) so unauthenticated
    callers cannot trigger agent-action approvals, rejections, or notifications.
    """
    raw_body = await request.body()
    app_secret = getattr(settings, "WHATSAPP_APP_SECRET", "")
    if not app_secret:
        raise HTTPException(503, "WhatsApp webhook not configured (WHATSAPP_APP_SECRET not set)")
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
                business_id, action_id = _parse_button_target(button_id)
                if business_id is None or action_id is None:
                    logger.warning("whatsapp_unresolvable_button button_id=%s", button_id)
                    await send_notification(
                        to_number=from_number,
                        text="⚠️ This action could not be located. Please approve or reject it from the NazmOS app.",
                    )
                    continue

                try:
                    if button_id.startswith("approve_price_shield_"):
                        result = await _run_tenant_scoped(
                            db, business_id,
                            lambda: run_agent_approval(db, action_id=action_id, business_id=business_id, note="Approved Price Shield via WhatsApp interactive button"),
                        )
                    elif button_id.startswith("approve_transfer_"):
                        result = await _run_tenant_scoped(
                            db, business_id,
                            lambda: run_agent_approval(db, action_id=action_id, business_id=business_id, note="Approved transfer via WhatsApp interactive button"),
                        )
                    elif button_id.startswith("reject_"):
                        result = await _run_tenant_scoped(
                            db, business_id,
                            lambda: run_agent_rejection(db, action_id=action_id, business_id=business_id, note="Rejected via WhatsApp interactive button"),
                        )
                        text = (
                            "❌ Action rejected. It has been dismissed from your NazmOS priority queue."
                            if result.get("ok")
                            else "⚠️ The action was not in a pending state; nothing was rejected."
                        )
                        await send_notification(to_number=from_number, text=text)
                        continue
                    elif button_id.startswith("approve_"):
                        result = await _run_tenant_scoped(
                            db, business_id,
                            lambda: run_agent_approval(db, action_id=action_id, business_id=business_id, note="Approved via WhatsApp interactive button"),
                        )
                    else:
                        logger.warning("whatsapp_unknown_button button_id=%s", button_id)
                        continue

                    outcome = result.get("outcome") or {}
                    if result.get("ok"):
                        text = f"✅ Action Approved. {outcome.get('action', 'Action processed')} via NazmOS."
                    else:
                        text = "⚠️ The action could not be approved (not pending, already processed, or out of scope)."
                    await send_notification(to_number=from_number, text=text)
                except Exception as exc:
                    logger.error(f"Error handling WhatsApp approval for action {action_id}: {exc}")
                    await send_notification(
                        to_number=from_number,
                        text="⚠️ The action could not be processed right now. Please try again from the NazmOS app.",
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
        result = await run_agent_approval(db, action_id=UUID(action_id), note="Simulated Test Approval")
    except Exception as exc:
        logger.warning(f"WhatsApp test approval could not run: {exc}")
        raise HTTPException(503, "WhatsApp approval simulation requires a reachable database")
    return {"ok": result.get("ok", False), "action_id": action_id, "simulated": "whatsapp_approve", "outcome": result.get("outcome")}
