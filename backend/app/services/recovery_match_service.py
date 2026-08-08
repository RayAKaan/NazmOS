"""Recovery Match service.

Manual-confirm R2R stock recovery. V1 intentionally avoids payments, escrow,
delivery, and regulated/near-expiry categories.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.money import sar, decimal_value

EXCLUDED_CATEGORY_KEYWORDS = [
    "medicine", "pharma", "drug", "baby", "formula", "dairy", "frozen", "meat", "cold", "cosmetic",
    "دواء", "صيد", "أطفال", "حليب أطفال", "مجمد", "لحم", "ألبان",
]
DEFAULT_MAX_DISTANCE_KM = Decimal("5.00")
MIN_FOOD_SHELF_LIFE_DAYS = 90
MIN_GENERAL_SHELF_LIFE_DAYS = 60


def _is_category_allowed(category: str | None, item_name: str | None, storage_type: str | None = None) -> bool:
    text_value = f"{category or ''} {item_name or ''} {storage_type or ''}".lower()
    return not any(k.lower() in text_value for k in EXCLUDED_CATEGORY_KEYWORDS)


def _expiry_is_safe(expiry_date: date | None, category: str | None, storage_type: str | None = None) -> tuple[bool, str | None]:
    if not expiry_date:
        return False, "expiry_date_required_for_real_match"
    days = (expiry_date - date.today()).days
    text_value = f"{category or ''} {storage_type or ''}".lower()
    min_days = MIN_FOOD_SHELF_LIFE_DAYS if any(k in text_value for k in ["food", "dates", "beverage", "snack", "قهوة", "تمر"]) else MIN_GENERAL_SHELF_LIFE_DAYS
    if days < min_days:
        return False, f"expiry_too_close_min_{min_days}_days"
    return True, None


def _distance_km(lat1, lon1, lat2, lon2) -> float | None:
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
    except Exception:
        return None
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _compute_match_score(listing_barcode: str | None, listing_sku: str | None, days_left: float, distance: float | None) -> int:
    score = 40
    if listing_barcode:
        score += 40
    elif listing_sku:
        score += 25
    score += max(0, 20 - int(days_left * 2))
    if distance is not None and distance <= 3:
        score += 5
    return min(score, 100)


async def log_recovery_event(db: AsyncSession, event_type: str, *, listing_id=None, match_id=None, actor_business_id=None, notes=None, payload=None) -> None:
    await db.execute(text("""
        INSERT INTO stock_recovery_events (id, listing_id, match_id, actor_business_id, event_type, notes, payload, created_at)
        VALUES (gen_random_uuid(), :listing_id, :match_id, :actor_business_id, :event_type, :notes, CAST(:payload AS JSON), NOW())
    """), {
        "listing_id": str(listing_id) if listing_id else None,
        "match_id": str(match_id) if match_id else None,
        "actor_business_id": str(actor_business_id) if actor_business_id else None,
        "event_type": event_type,
        "notes": notes,
        "payload": __import__('json').dumps(payload or {}),
    })


async def get_or_create_settings(db: AsyncSession, business_id: UUID | str) -> dict:
    res = await db.execute(text("SELECT * FROM recovery_match_settings WHERE business_id = :b"), {"b": str(business_id)})
    row = res.fetchone()
    if not row:
        res = await db.execute(text("""
            INSERT INTO recovery_match_settings (id, business_id, is_enabled, allow_contact_reveal, max_distance_km, created_at, updated_at)
            VALUES (gen_random_uuid(), :b, false, false, :dist, NOW(), NOW())
            RETURNING *
        """), {"b": str(business_id), "dist": DEFAULT_MAX_DISTANCE_KM})
        row = res.fetchone()
        await db.commit()
    return dict(row._mapping)


async def update_settings(db: AsyncSession, business_id: UUID | str, data: dict[str, Any]) -> dict:
    existing = await get_or_create_settings(db, business_id)
    await db.execute(text("""
        UPDATE recovery_match_settings
        SET is_enabled = COALESCE(:is_enabled, is_enabled),
            allow_contact_reveal = COALESCE(:allow_contact_reveal, allow_contact_reveal),
            max_distance_km = COALESCE(:max_distance_km, max_distance_km),
            allowed_categories = COALESCE(CAST(:allowed_categories AS JSON), allowed_categories),
            excluded_categories = COALESCE(CAST(:excluded_categories AS JSON), excluded_categories),
            updated_at = NOW()
        WHERE business_id = :business_id
    """), {
        "business_id": str(business_id),
        "is_enabled": data.get("is_enabled"),
        "allow_contact_reveal": data.get("allow_contact_reveal"),
        "max_distance_km": data.get("max_distance_km"),
        "allowed_categories": __import__('json').dumps(data.get("allowed_categories")) if data.get("allowed_categories") is not None else None,
        "excluded_categories": __import__('json').dumps(data.get("excluded_categories")) if data.get("excluded_categories") is not None else None,
    })
    await log_recovery_event(db, "settings_updated", actor_business_id=business_id, payload=data)
    await db.commit()
    return await get_or_create_settings(db, business_id)


async def generate_preview(db: AsyncSession, business_id: UUID | str) -> list[dict]:
    res = await db.execute(text("""
        WITH sales_30d AS (
            SELECT item_id, COALESCE(SUM(quantity), 0) AS qty_30d
            FROM transactions
            WHERE business_id = :business_id AND transaction_at >= NOW() - INTERVAL '30 days'
            GROUP BY item_id
        )
        SELECT i.id AS item_id, i.name AS item_name, i.sku, i.barcode, i.brand, i.pack_size, i.storage_type,
               c.name AS category_name, inv.current_stock, i.cost_price,
               GREATEST(COALESCE(s.qty_30d, 0) / 30.0, 0.01) AS daily_velocity,
               inv.current_stock / NULLIF(GREATEST(COALESCE(s.qty_30d, 0) / 30.0, 0.01), 0) AS days_of_supply
        FROM inventory inv
        JOIN items i ON i.id = inv.item_id
        LEFT JOIN categories c ON c.id = i.category_id
        LEFT JOIN sales_30d s ON s.item_id = i.id
        WHERE inv.business_id = :business_id AND i.business_id = :business_id AND inv.current_stock > 0
        ORDER BY days_of_supply DESC
        LIMIT 25
    """), {"business_id": str(business_id)})
    opportunities = []
    for row in res.fetchall():
        days = float(row.days_of_supply or 0)
        if days < 30:
            continue
        if not _is_category_allowed(row.category_name, row.item_name, row.storage_type):
            continue
        surplus_qty = max(0, float(row.current_stock or 0) - (float(row.daily_velocity or 0.01) * 14))
        if surplus_qty <= 0:
            continue
        cost = float(row.cost_price or 0)
        opportunities.append({
            "item_id": str(row.item_id),
            "item_name": row.item_name,
            "sku": row.sku,
            "barcode": row.barcode,
            "brand": row.brand,
            "pack_size": row.pack_size,
            "storage_type": row.storage_type,
            "category": row.category_name,
            "current_stock": float(row.current_stock or 0),
            "days_of_supply": round(days, 1),
            "estimated_surplus_qty": round(surplus_qty, 2),
            "estimated_recovery_value_sar": round(surplus_qty * cost * 0.80, 2),
            "status": "preview_only",
            "next_step": "Create a listing after confirming expiry, quantity, and price.",
        })
    return opportunities[:10]


async def create_listing(db: AsyncSession, business_id: UUID | str, data: dict[str, Any]) -> dict:
    settings = await get_or_create_settings(db, business_id)
    if not settings.get("is_enabled"):
        raise ValueError("Recovery Match must be enabled before creating listings")

    item_id = data["item_id"]
    res = await db.execute(text("""
        SELECT i.id, i.name, i.sku, i.barcode, i.brand, i.pack_size, i.storage_type, i.cost_price, c.name AS category_name
        FROM items i
        LEFT JOIN categories c ON c.id = i.category_id
        WHERE i.id = :item_id AND i.business_id = :business_id
    """), {"item_id": str(item_id), "business_id": str(business_id)})
    item = res.fetchone()
    if not item:
        raise ValueError("Item not found")
    if not _is_category_allowed(item.category_name, item.name, item.storage_type):
        raise ValueError("This category is excluded from Recovery Match v1")

    expiry = data.get("expiry_date")
    if isinstance(expiry, str):
        expiry = date.fromisoformat(expiry)
    safe, reason = _expiry_is_safe(expiry, item.category_name, item.storage_type)
    if not safe:
        raise ValueError(reason or "expiry_not_safe")

    qty = decimal_value(data.get("quantity_available"))
    cost = sar(item.cost_price or 0)
    discount_pct = decimal_value(data.get("discount_pct", 20))
    asking = data.get("asking_price_sar")
    asking_price = sar(asking if asking is not None else cost * (Decimal("1") - discount_pct / Decimal("100")))
    expires_at = datetime.now(timezone.utc) + timedelta(days=int(data.get("listing_days", 7)))

    res = await db.execute(text("""
        INSERT INTO stock_recovery_listings
            (id, seller_business_id, seller_branch_id, item_id, sku, barcode, item_name, brand, category,
             quantity_available, unit_cost_sar, asking_price_sar, discount_pct, expiry_date, batch_number,
             storage_type, status, notes, created_at, updated_at, expires_at)
        VALUES
            (gen_random_uuid(), :seller_business_id, :seller_branch_id, :item_id, :sku, :barcode, :item_name, :brand, :category,
             :quantity_available, :unit_cost_sar, :asking_price_sar, :discount_pct, :expiry_date, :batch_number,
             :storage_type, 'seller_approved', :notes, NOW(), NOW(), :expires_at)
        RETURNING *
    """), {
        "seller_business_id": str(business_id),
        "seller_branch_id": str(data.get("seller_branch_id") or business_id),
        "item_id": str(item.id),
        "sku": item.sku,
        "barcode": item.barcode,
        "item_name": item.name,
        "brand": item.brand,
        "category": item.category_name,
        "quantity_available": qty,
        "unit_cost_sar": cost,
        "asking_price_sar": asking_price,
        "discount_pct": discount_pct,
        "expiry_date": expiry,
        "batch_number": data.get("batch_number"),
        "storage_type": item.storage_type,
        "notes": data.get("notes"),
        "expires_at": expires_at,
    })
    row = res.fetchone()
    await log_recovery_event(db, "listing_created", listing_id=row.id, actor_business_id=business_id, payload={"item_name": item.name})
    await db.commit()
    return dict(row._mapping)


async def suggest_matches_for_listing(db: AsyncSession, listing_id: UUID | str, seller_business_id: UUID | str) -> list[dict]:
    listing_res = await db.execute(text("""
        SELECT l.*, sb.city AS seller_city, sb.latitude AS seller_lat, sb.longitude AS seller_lon
        FROM stock_recovery_listings l
        JOIN businesses sb ON sb.id = l.seller_business_id
        WHERE l.id = :listing_id AND l.seller_business_id = :seller_business_id
    """), {"listing_id": str(listing_id), "seller_business_id": str(seller_business_id)})
    listing = listing_res.fetchone()
    if not listing:
        raise ValueError("Listing not found")

    settings_res = await db.execute(text(
        "SELECT max_distance_km FROM recovery_match_settings WHERE business_id = :b"
    ), {"b": str(seller_business_id)})
    settings_row = settings_res.fetchone()
    max_distance = float(settings_row.max_distance_km) if settings_row else float(DEFAULT_MAX_DISTANCE_KM)

    candidates = await db.execute(text("""
        WITH sales_30d AS (
            SELECT business_id, item_id, COALESCE(SUM(quantity), 0) AS qty_30d
            FROM transactions
            WHERE transaction_at >= NOW() - INTERVAL '30 days'
            GROUP BY business_id, item_id
        )
        SELECT b.id AS buyer_business_id, b.name AS buyer_name, b.city, b.latitude, b.longitude,
               i.id AS buyer_item_id, inv.current_stock,
               GREATEST(COALESCE(s.qty_30d, 0) / 30.0, 0.01) AS daily_velocity,
               inv.current_stock / NULLIF(GREATEST(COALESCE(s.qty_30d, 0) / 30.0, 0.01), 0) AS days_left
        FROM businesses b
        JOIN recovery_match_settings rms ON rms.business_id = b.id AND rms.is_enabled = true
        JOIN items i ON i.business_id = b.id
        JOIN inventory inv ON inv.business_id = b.id AND inv.item_id = i.id
        LEFT JOIN sales_30d s ON s.business_id = b.id AND s.item_id = i.id
        WHERE b.id != :seller_business_id
          AND COALESCE(b.city, '') = COALESCE(:seller_city, '')
          AND (
            (CAST(:barcode AS TEXT) IS NOT NULL AND i.barcode = CAST(:barcode AS TEXT))
            OR (CAST(:barcode AS TEXT) IS NULL AND CAST(:sku AS TEXT) IS NOT NULL AND i.sku = CAST(:sku AS TEXT))
            OR (CAST(:barcode AS TEXT) IS NULL AND CAST(:sku AS TEXT) IS NULL AND LOWER(i.name) = LOWER(CAST(:item_name AS TEXT)))
          )
        LIMIT 50
    """), {
        "seller_business_id": str(seller_business_id),
        "seller_city": listing.seller_city,
        "barcode": listing.barcode,
        "sku": listing.sku,
        "item_name": listing.item_name,
    })

    created = []
    for c in candidates.fetchall():
        days_left = float(c.days_left or 999)
        if days_left > 7:
            continue
        distance = _distance_km(listing.seller_lat, listing.seller_lon, c.latitude, c.longitude)
        if distance is not None and distance > max_distance:
            continue
        score = _compute_match_score(listing.barcode, listing.sku, days_left, distance)
        if score < 75:
            continue
        buyer_need = max(1, (float(c.daily_velocity or 0.01) * 14) - float(c.current_stock or 0))
        res = await db.execute(text("""
            INSERT INTO stock_recovery_matches
                (id, listing_id, buyer_business_id, buyer_branch_id, buyer_item_id,
                 match_score, distance_km, buyer_need_qty, buyer_days_left, status, created_at, seller_approved_at)
            VALUES
                (gen_random_uuid(), :listing_id, :buyer_business_id, :buyer_branch_id, :buyer_item_id,
                 :score, :distance_km, :buyer_need_qty, :buyer_days_left, 'seller_interested', NOW(), NOW())
            ON CONFLICT (listing_id, buyer_business_id, buyer_item_id) DO UPDATE SET
                match_score = EXCLUDED.match_score,
                distance_km = EXCLUDED.distance_km,
                buyer_need_qty = EXCLUDED.buyer_need_qty,
                buyer_days_left = EXCLUDED.buyer_days_left,
                updated_at = NOW()
            RETURNING *
        """), {
            "listing_id": str(listing.id),
            "buyer_business_id": str(c.buyer_business_id),
            "buyer_branch_id": str(c.buyer_business_id),
            "buyer_item_id": str(c.buyer_item_id),
            "score": score,
            "distance_km": round(distance, 2) if distance is not None else None,
            "buyer_need_qty": round(buyer_need, 2),
            "buyer_days_left": round(days_left, 2),
        })
        row = res.fetchone()
        await log_recovery_event(db, "match_suggested", listing_id=listing.id, match_id=row.id, actor_business_id=seller_business_id)
        created.append(dict(row._mapping))
    await db.commit()
    return created


async def buyer_mark_interested(db: AsyncSession, match_id: UUID | str, buyer_business_id: UUID | str) -> dict:
    res = await db.execute(text("""
        UPDATE stock_recovery_matches
        SET status = CASE WHEN seller_approved_at IS NOT NULL THEN 'mutual_match' ELSE 'buyer_interested' END,
            buyer_approved_at = NOW(), updated_at = NOW()
        WHERE id = :match_id AND buyer_business_id = :buyer_business_id
        RETURNING *
    """), {"match_id": str(match_id), "buyer_business_id": str(buyer_business_id)})
    row = res.fetchone()
    if not row:
        raise ValueError("Match not found for buyer")
    await log_recovery_event(db, "buyer_interested", match_id=row.id, actor_business_id=buyer_business_id)
    await db.commit()
    return dict(row._mapping)


async def reveal_contact(db: AsyncSession, match_id: UUID | str, actor_business_id: UUID | str) -> dict:
    res = await db.execute(text("""
        SELECT m.*, l.seller_business_id, sb.name AS seller_name, sb.contact_phone AS seller_phone,
               bb.name AS buyer_name, bb.contact_phone AS buyer_phone
        FROM stock_recovery_matches m
        JOIN stock_recovery_listings l ON l.id = m.listing_id
        JOIN businesses sb ON sb.id = l.seller_business_id
        JOIN businesses bb ON bb.id = m.buyer_business_id
        WHERE m.id = :match_id
          AND (l.seller_business_id = :actor_business_id OR m.buyer_business_id = :actor_business_id)
    """), {"match_id": str(match_id), "actor_business_id": str(actor_business_id)})
    row = res.fetchone()
    if not row:
        raise ValueError("Match not found")
    if row.status != "mutual_match":
        raise ValueError("Contact can be revealed only after both sides approve")
    await db.execute(text("UPDATE stock_recovery_matches SET status='contact_revealed', contact_revealed_at=NOW(), updated_at=NOW() WHERE id=:id"), {"id": str(match_id)})
    await log_recovery_event(db, "contact_revealed", match_id=match_id, actor_business_id=actor_business_id)
    await db.commit()
    return {
        "seller": {"business_id": str(row.seller_business_id), "name": row.seller_name, "phone": row.seller_phone},
        "buyer": {"business_id": str(row.buyer_business_id), "name": row.buyer_name, "phone": row.buyer_phone},
        "message": "Contact details revealed. Payment, pickup, and inspection are handled directly between merchants.",
    }


async def complete_match(db: AsyncSession, match_id: UUID | str, actor_business_id: UUID | str, recovered_value_sar) -> dict:
    value = sar(recovered_value_sar)
    res = await db.execute(text("""
        UPDATE stock_recovery_matches
        SET status='completed', completed_at=NOW(), recovered_value_sar=:value, updated_at=NOW()
        WHERE id=:match_id
        RETURNING *
    """), {"match_id": str(match_id), "value": value})
    row = res.fetchone()
    if not row:
        raise ValueError("Match not found")
    await log_recovery_event(db, "completed", match_id=match_id, actor_business_id=actor_business_id, payload={"recovered_value_sar": float(value)})
    await db.commit()
    return dict(row._mapping)


async def reject_match(db: AsyncSession, match_id: UUID | str, actor_business_id: UUID | str, reason: str | None = None) -> dict:
    res = await db.execute(text("""
        SELECT m.*, l.seller_business_id
        FROM stock_recovery_matches m
        JOIN stock_recovery_listings l ON l.id = m.listing_id
        WHERE m.id = :match_id
          AND (m.buyer_business_id = :actor_business_id OR l.seller_business_id = :actor_business_id)
    """), {"match_id": str(match_id), "actor_business_id": str(actor_business_id)})
    row = res.fetchone()
    if not row:
        raise ValueError("Match not found")

    await db.execute(text("""
        UPDATE stock_recovery_matches
        SET status = 'rejected', updated_at = NOW()
        WHERE id = :match_id
    """), {"match_id": str(match_id)})
    await log_recovery_event(
        db,
        "rejected",
        match_id=match_id,
        listing_id=row.listing_id,
        actor_business_id=actor_business_id,
        notes=reason,
    )
    await db.commit()
    return {"ok": True, "match_id": str(match_id), "status": "rejected"}


async def report_match_issue(
    db: AsyncSession,
    match_id: UUID | str,
    actor_business_id: UUID | str,
    issue_type: str,
    notes: str | None = None,
) -> dict:
    res = await db.execute(text("""
        SELECT m.*, l.seller_business_id
        FROM stock_recovery_matches m
        JOIN stock_recovery_listings l ON l.id = m.listing_id
        WHERE m.id = :match_id
          AND (m.buyer_business_id = :actor_business_id OR l.seller_business_id = :actor_business_id)
    """), {"match_id": str(match_id), "actor_business_id": str(actor_business_id)})
    row = res.fetchone()
    if not row:
        raise ValueError("Match not found")

    await db.execute(text("""
        UPDATE stock_recovery_matches
        SET status = CASE WHEN status = 'completed' THEN status ELSE 'issue_reported' END,
            updated_at = NOW()
        WHERE id = :match_id
    """), {"match_id": str(match_id)})
    await log_recovery_event(
        db,
        "issue_reported",
        match_id=match_id,
        listing_id=row.listing_id,
        actor_business_id=actor_business_id,
        notes=notes,
        payload={"issue_type": issue_type},
    )
    await db.commit()
    return {"ok": True, "match_id": str(match_id), "issue_type": issue_type, "status": "issue_reported"}


async def activate_recovery_match(
    db: AsyncSession,
    business_id: UUID | str,
    auto_create_listings: bool = False,
    max_listings: int = 3,
) -> dict:
    """Activate Recovery Match for a business and optionally seed listings from preview.

    This is the "beyond preview" activation path: it enables the feature, sets
    sensible defaults, and can create the first seller listings automatically
    from the top surplus opportunities.
    """
    settings = await update_settings(db, business_id, {
        "is_enabled": True,
        "allow_contact_reveal": False,
        "max_distance_km": 5,
    })

    created_listings: list[dict] = []
    if auto_create_listings:
        opportunities = await generate_preview(db, business_id)
        # Only auto-list items with long shelf-life categories and safe surplus.
        for opp in opportunities[:max_listings]:
            if opp.get("status") != "preview_only":
                continue
            try:
                listing = await create_listing(db, business_id, {
                    "item_id": opp["item_id"],
                    "quantity_available": opp.get("estimated_surplus_qty", 1),
                    "discount_pct": 20,
                    "expiry_date": (date.today() + timedelta(days=180)).isoformat(),
                    "listing_days": 14,
                    "notes": "Auto-created during Recovery Match activation",
                })
                created_listings.append(listing)
            except ValueError:
                # Some items may fail category/expiry safety checks; skip them.
                continue

    return {
        "activated": True,
        "settings": settings,
        "auto_create_listings": auto_create_listings,
        "listings_created": len(created_listings),
        "listings": created_listings,
        "next_step": "Go to Recovery Match > My Listings and click 'Suggest Nearby Buyers'.",
    }
