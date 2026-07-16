"""
NazmOS Universal Inventory Orchestrator
Location-aware demand forecasting and inter-branch stock rebalancing.

This implementation is aligned to the current schema:
- branches are rows in businesses under the same organization_id;
- stock lives in inventory.current_stock;
- item cost lives in items.cost_price;
- demand velocity is inferred from transactions over the last 30 days.
"""
import logging
from typing import Dict, Any, List
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("inventory_orchestrator")


async def analyze_inter_branch_rebalancing(db: AsyncSession, business_id: UUID) -> Dict[str, Any]:
    """
    Analyze stock levels across branches belonging to the same organization.

    If one branch has excess supply (>45 days) while another has shortage risk (<7 days),
    recommend an internal transfer before creating an external supplier PO.
    """
    query = text("""
        WITH root_business AS (
            SELECT id, organization_id
            FROM businesses
            WHERE id = :b
        ), branch_stock AS (
            SELECT
                b.id AS branch_id,
                COALESCE(b.location_name, b.name) AS branch_name,
                b.city,
                COALESCE(NULLIF(i.sku, ''), LOWER(TRIM(i.name))) AS product_key,
                i.id AS item_id,
                i.name AS item_name,
                i.sku,
                i.cost_price,
                inv.current_stock,
                GREATEST(
                    COALESCE(SUM(t.quantity) FILTER (
                        WHERE t.transaction_at >= NOW() - INTERVAL '30 days'
                    ), 0) / 30.0,
                    0.01
                ) AS daily_velocity
            FROM root_business rb
            JOIN businesses b ON (
                (rb.organization_id IS NOT NULL AND b.organization_id = rb.organization_id)
                OR b.id = rb.id
            )
            JOIN items i ON i.business_id = b.id AND i.is_active = true
            JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = b.id
            LEFT JOIN transactions t ON t.item_id = i.id AND t.business_id = b.id
            GROUP BY
                b.id, b.location_name, b.name, b.city,
                product_key, i.id, i.name, i.sku, i.cost_price, inv.current_stock
        )
        SELECT
            *,
            current_stock / NULLIF(daily_velocity, 0) AS days_of_supply
        FROM branch_stock
        ORDER BY product_key, days_of_supply DESC
    """)

    try:
        res = await db.execute(query, {"b": str(business_id)})
        rows = [dict(r._mapping) for r in res.fetchall()]
    except Exception as e:
        logger.warning(f"Rebalancing query failed: {e}")
        rows = []

    product_map: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("product_key") or row.get("item_id"))
        product_map.setdefault(key, []).append(row)

    transfers = []
    total_capital_saved = 0.0

    for _, branches in product_map.items():
        if len(branches) < 2:
            continue

        overstocked = [b for b in branches if float(b.get("days_of_supply") or 0) > 45.0]
        understocked = [b for b in branches if float(b.get("days_of_supply") or 0) < 7.0]

        for source in overstocked:
            for dest in understocked:
                if str(source["branch_id"]) == str(dest["branch_id"]):
                    continue

                source_velocity = float(source.get("daily_velocity") or 0.01)
                dest_velocity = float(dest.get("daily_velocity") or 0.01)
                source_stock = float(source.get("current_stock") or 0)
                dest_stock = float(dest.get("current_stock") or 0)

                surplus_qty = source_stock - (source_velocity * 20.0)
                deficit_qty = (dest_velocity * 14.0) - dest_stock
                transfer_qty = min(surplus_qty, deficit_qty)

                if transfer_qty <= 0:
                    continue

                saved_value = transfer_qty * float(source.get("cost_price") or 0)
                total_capital_saved += saved_value

                transfers.append({
                    "item_id": str(source["item_id"]),
                    "item_name": source["item_name"],
                    "sku": source.get("sku") or "",
                    "from_business_id": str(source["branch_id"]),
                    "from_location_name": source["branch_name"],
                    "to_business_id": str(dest["branch_id"]),
                    "to_location_name": dest["branch_name"],
                    "recommended_transfer_qty": round(transfer_qty, 2),
                    "capital_saved_sar": round(saved_value, 2),
                    "reason": (
                        f"Transfer surplus from {source['branch_name']} "
                        f"({float(source.get('days_of_supply') or 0):.1f}d supply) "
                        f"to prevent stockout at {dest['branch_name']} "
                        f"({float(dest.get('days_of_supply') or 0):.1f}d supply)."
                    ),
                })

    return {
        "status": "ORCHESTRATED",
        "total_products_evaluated": len(product_map),
        "suggested_transfers_count": len(transfers),
        "total_working_capital_saved_sar": round(total_capital_saved, 2),
        "transfers": transfers,
        "note": "Inter-branch transfers reduce unnecessary external purchasing and prevent branch-level stockouts.",
    }
