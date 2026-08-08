"""
Foodics POS Adapter: Real-time order webhooks for Retail Recovery.

Core responsibility now:
- enforce idempotency
- deduct inventory
- record transaction ledger

Live tax clearance is intentionally not part of the core NazmOS product surface.
If customers need compliance services, they are handled later outside the core recovery workflow.
"""
import logging
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.money import sar, decimal_value
from app.adapters.item_resolver import resolve_item

logger = logging.getLogger("foodics_adapter")


async def handle_foodics_order_created(payload: Dict[str, Any], business_id: UUID, db: AsyncSession) -> Dict[str, Any]:
    """Parse Foodics order, prevent duplicate processing, deduct stock, and record sales."""
    order_ref = str(payload.get("reference") or payload.get("id") or f"FD-{datetime.now().strftime('%H%M%S')}")
    products = payload.get("products", [])
    logger.info(f"Processing Foodics order webhook {order_ref} with {len(products)} products for business {business_id}")

    existing = await db.execute(
        text("SELECT id FROM transactions WHERE business_id = :b AND reference_id = :ref LIMIT 1"),
        {"b": str(business_id), "ref": order_ref},
    )
    if existing.fetchone():
        return {"status": "SKIPPED_DUPLICATE", "pos_reference": order_ref, "note": "Order already processed."}

    transactions_recorded = 0
    inventory_deducted = 0
    total_amount = Decimal("0.00")
    unresolved: list[str] = []

    for product in products:
        name = str(product.get("name", "Item"))
        sku = str(product.get("sku") or product.get("code") or "")
        barcode = str(product.get("barcode") or product.get("ean") or "")
        qty = decimal_value(product.get("quantity", 1))
        price = sar(product.get("unit_price", 0.0))
        line_total = sar(qty * price)
        fallback_cost = sar(price * Decimal("0.70"))
        total_amount = sar(total_amount + line_total)

        item = await resolve_item(db, business_id, name, sku=sku, barcode=barcode)
        if item is None:
            unresolved.append(name)
            continue

        inv_result = await db.execute(text("""
            UPDATE inventory inv
            SET current_stock = GREATEST(0, current_stock - :q),
                updated_at = NOW()
            WHERE inv.item_id = :item_id
              AND inv.business_id = :b
            RETURNING inv.id
        """), {"q": qty, "b": str(business_id), "item_id": str(item["id"])})
        if inv_result.fetchone():
            inventory_deducted += 1

        tx_result = await db.execute(text("""
            INSERT INTO transactions
                (id, business_id, item_id, quantity, unit_price, cost_price,
                 total_amount, profit, reference_id, transaction_at)
            VALUES
                (gen_random_uuid(), :b, :item_id, :q, :p,
                 COALESCE(:cost_price, :fallback_cost),
                 :total,
                 (:p - COALESCE(:cost_price, :fallback_cost)) * :q,
                 :ref,
                 NOW())
            RETURNING id
        """), {
            "b": str(business_id),
            "item_id": str(item["id"]),
            "q": qty,
            "p": price,
            "cost_price": item.get("cost_price"),
            "fallback_cost": fallback_cost,
            "total": line_total,
            "ref": order_ref,
        })
        if tx_result.fetchone():
            transactions_recorded += 1

    await db.commit()
    result = {
        "status": "PROCESSED",
        "pos_reference": order_ref,
        "items_received": len(products),
        "inventory_deducted": inventory_deducted,
        "transactions_recorded": transactions_recorded,
        "total_amount_sar": float(total_amount),
        "note": "Retail Recovery ledger updated. Certified tax invoicing is a partner add-on, not part of this webhook.",
    }
    if unresolved:
        result["unresolved_items"] = unresolved[:10]
        result["note"] += f" {len(unresolved)} item(s) could not be matched to the catalog."
    return result
