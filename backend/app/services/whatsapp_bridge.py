"""
WhatsApp Business Cloud API – Approval bridge
KSA – Mock mode by default ($0)
Set WHATSAPP_ENABLED=live + WHATSAPP_TOKEN to go live
"""
import os
import logging
import httpx
import urllib.parse
from typing import Dict, Any

logger = logging.getLogger("whatsapp")

WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "mock").lower()
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")


def generate_deep_link(phone: str, message: str) -> str:
    """Generate a wa.me deep link for zero-cost WhatsApp messaging.

    Falls back to this when WHATSAPP_ENABLED != 'live' or user is on free tier.
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
    Send interactive approval message via WhatsApp
    Mock mode: logs to console + returns fake message_id
    Live mode: POST to graph.facebook.com/v21.0/{phone_id}/messages
    """
    if WHATSAPP_ENABLED != "live" or not WHATSAPP_TOKEN:
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
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
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
            return r.json()
        except Exception as e:
            logger.error(f"Failed to send live WhatsApp approval: {e}")
            return {"status": "error", "error": str(e)}


async def send_notification(to_number: str, text: str) -> Dict[str, Any]:
    """Simple text notification – supports both mock and live mode"""
    if WHATSAPP_ENABLED != "live" or not WHATSAPP_TOKEN:
        logger.info(f"[WHATSAPP MOCK] Notify {to_number}: {text[:80]}")
        return {"status": "mock_sent"}
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to_number,
                    "type": "text",
                    "text": {"body": text}
                },
                timeout=10.0
            )
            return r.json()
        except Exception as e:
            logger.error(f"Failed to send live WhatsApp notification: {e}")
            return {"status": "error", "error": str(e)}
