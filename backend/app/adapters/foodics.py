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

    for product in products:
        name = str(product.get("name", "Item"))
        qty = decimal_value(product.get("quantity", 1))
        price = sar(product.get("unit_price", 0.0))
        line_total = sar(qty * price)
        fallback_cost = sar(price * Decimal("0.70"))
        total_amount = sar(total_amount + line_total)

        inv_result = await db.execute(text("""
            UPDATE inventory inv
            SET current_stock = GREATEST(0, current_stock - :q),
                updated_at = NOW()
            FROM items i
            WHERE inv.item_id = i.id
              AND i.business_id = :b
              AND i.name ILIKE :name
            RETURNING inv.id
        """), {"q": qty, "b": str(business_id), "name": f"%{name[:10]}%"})
        if inv_result.fetchone():
            inventory_deducted += 1

        tx_result = await db.execute(text("""
            INSERT INTO transactions
                (id, business_id, item_id, quantity, unit_price, cost_price,
                 total_amount, profit, reference_id, transaction_at)
            SELECT gen_random_uuid(), :b, i.id, :q, :p,
                   COALESCE(i.cost_price, :fallback_cost),
                   :total,
                   (:p - COALESCE(i.cost_price, :fallback_cost)) * :q,
                   :ref,
                   NOW()
            FROM items i
            WHERE i.business_id = :b AND i.name ILIKE :name
            LIMIT 1
            RETURNING id
        """), {
            "b": str(business_id),
            "q": qty,
            "p": price,
            "fallback_cost": fallback_cost,
            "total": line_total,
            "ref": order_ref,
            "name": f"%{name[:10]}%",
        })
        if tx_result.fetchone():
            transactions_recorded += 1

    await db.commit()
    return {
        "status": "PROCESSED",
        "pos_reference": order_ref,
        "items_received": len(products),
        "inventory_deducted": inventory_deducted,
        "transactions_recorded": transactions_recorded,
        "total_amount_sar": float(total_amount),
        "note": "Retail Recovery ledger updated. Certified tax invoicing is a partner add-on, not part of this webhook.",
    }
