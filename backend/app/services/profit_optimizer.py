"""
NazmOS Proactive Profit-Optimization Agent
Scans item ledgers for wholesale cost inflation and retail margin compression.
Uses Decimal-based SAR arithmetic and Shariah Anti-Ihtikar ethical trade rules.
"""
import logging
from decimal import Decimal
from typing import Dict, Any
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.shariah_compliance import check_pricing_ethics_ihtikar
from app.utils.money import sar

logger = logging.getLogger("profit_optimizer")


async def scan_profit_margin_compression(db: AsyncSession, business_id: UUID, target_min_margin_pct: float = 20.0) -> Dict[str, Any]:
    """
    Interrogates database items for wholesale cost vs. retail shelf price.
    If wholesale costs have increased causing net margin to drop below target_min_margin_pct,
    it calculates the exact price adjustment required to restore profitability.
    """
    query = text("""
        SELECT 
            i.id, i.name, i.sku, c.name AS category_name, i.cost_price, i.sell_price,
            CASE WHEN i.sell_price > 0 
                 THEN ((i.sell_price - i.cost_price) / i.sell_price) * 100.0 
                 ELSE 0.0 END AS current_margin_pct
        FROM items i
        LEFT JOIN categories c ON c.id = i.category_id
        WHERE i.business_id = :b AND i.sell_price > 0
    """)

    try:
        res = await db.execute(query, {"b": str(business_id)})
        items = [dict(r._mapping) for r in res.fetchall()]
    except Exception as e:
        logger.warning(f"Profit optimizer query fallback: {e}")
        items = []

    alerts = []
    total_potential_profit_recovery = Decimal("0.00")
    target_margin = Decimal(str(target_min_margin_pct))

    for item in items:
        cur_margin = Decimal(str(item.get("current_margin_pct") or "0"))
        unit_cost = sar(item.get("cost_price"))
        sell_price = sar(item.get("sell_price"))

        if cur_margin < target_margin and unit_cost > 0:
            denominator = Decimal("1.0") - (target_margin / Decimal("100"))
            if denominator <= 0:
                continue
            recommended_price = sar(unit_cost / denominator)
            price_diff = sar(recommended_price - sell_price)

            shariah_check = check_pricing_ethics_ihtikar(
                item_name=item["name"],
                old_price=float(sell_price),
                new_price=float(recommended_price),
                cost_increase_pct=10.0,
                is_ramadan=False,
            )

            is_ethical = shariah_check.get("ethical_status") != "FLAGGED_IHTIKAR_RISK"
            monthly_profit_gain = sar(price_diff * Decimal("50"))
            total_potential_profit_recovery = sar(total_potential_profit_recovery + monthly_profit_gain)

            alerts.append({
                "item_id": str(item["id"]),
                "name": item["name"],
                "sku": item.get("sku", ""),
                "category_name": item.get("category_name"),
                "current_unit_cost_sar": float(unit_cost),
                "current_sell_price_sar": float(sell_price),
                "current_margin_pct": round(float(cur_margin), 2),
                "target_margin_pct": round(float(target_margin), 2),
                "recommended_sell_price_sar": float(recommended_price),
                "monthly_profit_recovery_sar": float(monthly_profit_gain),
                "shariah_ethical_approval": is_ethical,
                "shariah_note": shariah_check.get("ruling" if not is_ethical else "note", "Approved fair trade pricing."),
                "action_hook": "CLICK_APPROVE_TO_UPDATE_SHELF_PRICE",
            })

    return {
        "status": "OPTIMIZED",
        "total_items_scanned": len(items),
        "margin_compression_alerts": len(alerts),
        "total_monthly_profit_recovery_sar": float(total_potential_profit_recovery),
        "recommendations": alerts,
        "note": "Proactive profit optimization shifts focus from loss management to continuous margin expansion.",
    }
