from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from datetime import datetime, timedelta

from app.middleware.auth_middleware import get_current_user
from app.database import get_db, User
from app.services.decision_engine import DecisionEngine

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


@router.get("/recommend")
async def get_recommendations(
    business_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT i.id, i.name, i.unit, i.cost_price, i.sell_price,
                   inv.current_stock, inv.reorder_level, inv.max_stock,
                   (SELECT COALESCE(AVG(quantity), 0)
                    FROM transactions t
                    WHERE t.item_id = i.id AND t.transaction_at >= NOW() - INTERVAL '30 days') as daily_avg_30d,
                   (SELECT COALESCE(AVG(quantity), 0)
                    FROM transactions t
                    WHERE t.item_id = i.id AND t.transaction_at >= NOW() - INTERVAL '7 days') as daily_avg_7d,
                   (SELECT COALESCE(SUM(quantity), 0)
                    FROM transactions t
                    WHERE t.item_id = i.id AND t.transaction_at >= NOW() - INTERVAL '30 days') as total_30d
            FROM items i
            JOIN inventory inv ON inv.item_id = i.id
            WHERE i.business_id = :business_id AND i.is_active = true
        """),
        {"business_id": business_id}
    )
    items = result.fetchall()

    inventory_items = []
    for item in items:
        daily_avg = float(item.daily_avg_30d) / 30 if item.daily_avg_30d else 0
        days_left = float(item.current_stock) / daily_avg if daily_avg > 0.1 else 999
        
        prev_7d = float(item.daily_avg_7d) if item.daily_avg_7d else 0
        curr_7d = daily_avg * 7
        trend = "stable"
        if curr_7d > prev_7d * 1.1:
            trend = "up"
        elif curr_7d < prev_7d * 0.9:
            trend = "down"

        inventory_items.append({
            "item_id": str(item.id),
            "name": item.name,
            "unit": item.unit,
            "current_stock": float(item.current_stock),
            "daily_avg_sale": round(daily_avg, 2),
            "days_until_stockout": round(days_left, 1),
            "cost_price": float(item.cost_price),
            "sell_price": float(item.sell_price),
            "reorder_level": float(item.reorder_level),
            "trend_7d": trend,
        })

    engine = DecisionEngine()
    decisions = engine.generate_from_inventory(inventory_items)

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "decisions": [d.to_dict() for d in decisions],
        "summary": {
            "total_decisions": len(decisions),
            "urgent_count": sum(1 for d in decisions if d.priority == 1),
            "total_restock_value": sum(
                d.estimated_value or 0 for d in decisions if d.action.value == "RESTOCK"
            ),
            "total_potential_recovered": sum(
                d.estimated_value or 0 for d in decisions if d.action.value == "DISCOUNT"
            ),
        },
    }


@router.post("/apply/{decision_id}")
async def apply_decision(
    decision_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    from app.services.cache_service import CacheService

    await db.execute(
        text("""
            UPDATE decision_log
            SET was_applied = true, applied_at = NOW()
            WHERE id = :id
        """),
        {"id": decision_id}
    )
    await db.commit()

    return {"status": "applied", "decision_id": decision_id}
