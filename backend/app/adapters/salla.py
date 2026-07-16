"""
Salla E-Commerce Adapter: Real-time order webhook processing for Retail Recovery.

Core responsibility now:
- enforce idempotency
- deduct inventory
- record transaction ledger

Live tax clearance/reporting is intentionally outside the core product surface.
"""
import logging
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.money import sar, decimal_value

logger = logging.getLogger("salla_adapter")


async def handle_salla_order_created(payload: Dict[str, Any], business_id: UUID, db: AsyncSession) -> Dict[str, Any]:
    """Parse Salla order.created payload, prevent duplicates, deduct stock, and record sales."""
    order = payload.get("data", {}) if "data" in payload else payload
    order_id = str(order.get("id") or order.get("reference_id") or f"SAL-{datetime.now().strftime('%H%M%S')}")
    items = order.get("items", [])
    logger.info(f"Processing Salla order webhook {order_id} for business {business_id}")

    existing = await db.execute(
        text("SELECT id FROM transactions WHERE business_id = :b AND reference_id = :ref LIMIT 1"),
        {"b": str(business_id), "ref": order_id},
    )
    if existing.fetchone():
        return {"status": "SKIPPED_DUPLICATE", "salla_order_id": order_id, "note": "Order already processed."}

    transactions_recorded = 0
    inventory_deducted = 0
    total_amount = Decimal("0.00")

    for item in items:
        name = str(item.get("name", "Product"))
        qty = decimal_value(item.get("quantity", 1))
        amounts = item.get("amounts", {})
        price = sar(amounts.get("price_without_tax", {}).get("amount", 20.0))
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
            "ref": order_id,
            "name": f"%{name[:10]}%",
        })
        if tx_result.fetchone():
            transactions_recorded += 1

    await db.commit()
    return {
        "status": "PROCESSED",
        "salla_order_id": order_id,
        "items_received": len(items),
        "inventory_deducted": inventory_deducted,
        "transactions_recorded": transactions_recorded,
        "total_amount_sar": float(total_amount),
        "note": "Retail Recovery ledger updated. Certified tax invoicing is a partner add-on, not part of this webhook.",
    }
