"""
WhatsApp Business Cloud API – Approval bridge
KSA – Mock mode by default ($0)
Set WHATSAPP_ENABLED=live + WHATSAPP_TOKEN + WHATSAPP_PHONE_ID to go live.

Live-mode Meta API failures (expired token, invalid phone ID, rate limit) are
logged and fall back to a wa.me deep link so the merchant still has a path to
approve — delivery must never silently fail or block agent action creation.
"""
import logging
import httpx
import urllib.parse
from typing import Dict, Any

from app.config import get_settings

logger = logging.getLogger("whatsapp")

settings = get_settings()


def _is_live() -> bool:
    return settings.WHATSAPP_ENABLED == "live" and bool(settings.WHATSAPP_TOKEN)


def generate_deep_link(phone: str, message: str) -> str:
    """Generate a wa.me deep link for zero-cost WhatsApp messaging.

    Falls back to this when WHATSAPP_ENABLED != 'live' or when a live send fails.
    Opens WhatsApp on mobile / WhatsApp Web on desktop.
    """
    clean_phone = phone.replace("+", "").replace("-", "").replace(" ", "")
    encoded = urllib.parse.quote(message)
    return f"https://wa.me/{clean_phone}?text={encoded}"


async def send_approval_request(
    to_number: str,
    action_id: str,
    title: str,
    summary: str,
    approve_url: str,
    reject_url: str,
    approve_title: str = "✅ Approve",
    reject_title: str = "❌ Reject",
    action_prefix: str = "approve",
) -> Dict[str, Any]:
    """
    Send interactive approval message via WhatsApp.
    Mock mode: logs to console + returns fake message_id.
    Live mode: POST to graph.facebook.com/v21.0/{phone_id}/messages, falling
    back to a deep link on any Meta API error.
    """
    if not _is_live():
        # Mock – $0 – perfect for pilot clients
        logger.info(f"[WHATSAPP MOCK] To {to_number} – {title}")
        logger.info(f"  Approve: {approve_url}")
        logger.info(f"  Reject: {reject_url}")
        return {
            "status": "mock_sent",
            "message_id": f"mock_wamid_{action_id}",
            "to": to_number,
        }

    # Live WhatsApp Cloud API
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to_number,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {"text": f"{title}\n\n{summary}"},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": f"{action_prefix}_{action_id}", "title": approve_title}},
                                {"type": "reply", "reply": {"id": f"reject_{action_id}", "title": reject_title}},
                            ]
                        }
                    }
                },
                timeout=10.0
            )
            body = r.json()
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"WhatsApp API error {r.status_code}: {body}", request=r.request, response=r
                )
            return body
    except Exception as e:
        logger.error(f"Failed to send live WhatsApp approval: {e} — falling back to deep link")
        fallback_msg = f"{title}\n\n{summary}\n\nApprove: {approve_url}\nReject: {reject_url}"
        return {
            "status": "deep_link_fallback",
            "message_id": f"fallback_{action_id}",
            "to": to_number,
            "deep_link": generate_deep_link(to_number, fallback_msg),
        }


async def send_notification(to_number: str, text: str) -> Dict[str, Any]:
    """Simple text notification – supports both mock and live mode."""
    if not _is_live():
        logger.info(f"[WHATSAPP MOCK] Notify {to_number}: {text[:80]}")
        return {"status": "mock_sent"}

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to_number,
                    "type": "text",
                    "text": {"body": text}
                },
                timeout=10.0
            )
            body = r.json()
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"WhatsApp API error {r.status_code}: {body}", request=r.request, response=r
                )
            return body
    except Exception as e:
        logger.error(f"Failed to send live WhatsApp notification: {e} — falling back to deep link")
        return {
            "status": "deep_link_fallback",
            "message_id": "fallback",
            "to": to_number,
            "deep_link": generate_deep_link(to_number, text),
        }
