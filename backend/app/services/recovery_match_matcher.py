"""Nightly Recovery Match liquidity job.

Scans all active listings, suggests matches, and notifies both sides via
WhatsApp when a strong mutual opportunity is found.  This is intended to run
as a Celery beat task or as a manual endpoint for pilot validation.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.recovery_match_service import suggest_matches_for_listing
from app.services.whatsapp_bridge import send_notification

logger = logging.getLogger(__name__)


async def _notify_business(db: AsyncSession, business_id: str, message: str) -> dict[str, Any]:
    """Send a WhatsApp notification to the primary contact of a business."""
    res = await db.execute(
        text("""
            SELECT u.phone, b.name
            FROM businesses b
            JOIN users u ON u.id = b.owner_id
            WHERE b.id = :business_id
        """),
        {"business_id": business_id},
    )
    row = res.fetchone()
    if not row or not row.phone:
        return {"status": "no_contact", "business_id": business_id}

    result = await send_notification(row.phone, message)
    return {
        "status": result.get("status"),
        "business_id": business_id,
        "business_name": row.name,
        "phone": row.phone,
    }


async def run_nightly_recovery_match_scan(db: AsyncSession) -> dict[str, Any]:
    """Run the matcher across all active listings and notify merchants.

    Returns a summary of listings scanned, matches created, and notifications
    sent so it can be logged/alerted on.
    """
    listings_res = await db.execute(
        text("""
            SELECT id, seller_business_id, item_name, quantity_available, asking_price_sar
            FROM stock_recovery_listings
            WHERE status = 'seller_approved'
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
        """)
    )
    listings = listings_res.fetchall()

    total_listings = len(listings)
    total_matches = 0
    notifications = []

    for listing in listings:
        try:
            matches = await suggest_matches_for_listing(db, listing.id, listing.seller_business_id)
        except Exception as exc:
            logger.warning(
                "recovery_match_suggest_failed",
                extra={"listing_id": str(listing.id), "error": str(exc)},
            )
            continue

        total_matches += len(matches)

        for match in matches:
            if match.get("match_score", 0) < 85:
                continue

            seller_msg = (
                f"Nazm Recovery Match: a nearby retailer may need your "
                f"*{listing.item_name}* (qty {listing.quantity_available}). "
                f"Open NazmOS to approve the match."
            )
            seller_notify = await _notify_business(db, str(listing.seller_business_id), seller_msg)
            notifications.append(seller_notify)

            buyer_msg = (
                f"Nazm Recovery Match: *{listing.item_name}* is available nearby "
                f"at a discount. Open NazmOS to express interest."
            )
            buyer_notify = await _notify_business(db, str(match["buyer_business_id"]), buyer_msg)
            notifications.append(buyer_notify)

    summary = {
        "listings_scanned": total_listings,
        "matches_created": total_matches,
        "notifications_sent": len([n for n in notifications if n.get("status") == "mock_sent"]),
        "notifications_failed": len([n for n in notifications if n.get("status") != "mock_sent"]),
    }
    logger.info("recovery_match_nightly_scan_complete", extra=summary)
    return summary
