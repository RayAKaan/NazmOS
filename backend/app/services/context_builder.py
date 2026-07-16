"""
NazmOS Context Builder (KSA Edition)
Compiles merchant operating context from the primary PostgreSQL retail ledger.

Production rule: Postgres is the source of truth. Optional retrieval sidecars are not part
of the core product path.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytz
from sqlalchemy import text

KSA = pytz.timezone("Asia/Riyadh")


class ContextBuilder:
    def __init__(self, business_id: str):
        self.business_id = business_id

    async def retrieve_ai_memory_context(self, query_text: str, db: Any) -> List[Dict[str, Any]]:
        """Retrieve lightweight context from the primary Postgres retail ledger."""
        try:
            res = await db.execute(text("""
                SELECT i.name, i.sku, i.barcode, inv.current_stock, i.sell_price, i.cost_price, c.name AS category
                FROM items i
                JOIN inventory inv ON i.id = inv.item_id
                LEFT JOIN categories c ON c.id = i.category_id
                WHERE i.business_id = :b
                  AND (
                    i.name ILIKE :q
                    OR i.sku ILIKE :q
                    OR i.barcode ILIKE :q
                    OR c.name ILIKE :q
                  )
                LIMIT 8
            """), {"b": str(self.business_id), "q": f"%{query_text[:40]}%"})
            rows = [dict(r._mapping) for r in res.fetchall()]
            return [{"source": "Postgres_Retail_Ledger", "data": rows}] if rows else []
        except Exception:
            return []

    async def build(self, db, kpis: dict, alerts: list, top_items: list,
                    inventory_items: list, dead_stock: list, forecasts: dict, patterns: dict) -> dict:
        now = datetime.now(KSA)
        today = now.date()

        from app.utils.saudi_holidays import get_next_festival
        next_festival = get_next_festival(today)

        return {
            "business": {
                "business_id": str(self.business_id),
                "today_date": today.isoformat(),
                "day_of_week": today.strftime("%A"),
                "current_time": now.strftime("%I:%M %p KSA"),
            },
            "kpis": kpis,
            "alerts": alerts[:10] if alerts else [],
            "top_items_7d": top_items[:15] if top_items else [],
            "inventory_critical": [
                item for item in inventory_items
                if item.get("days_left", 999) < 5
            ] if inventory_items else [],
            "dead_stock": dead_stock[:10] if dead_stock else [],
            "forecasts": forecasts,
            "patterns": patterns or {
                "best_day_of_week": "Friday (Jumu'ah)",
                "worst_day_of_week": "Tuesday",
                "tuesday_dip_pct": 28,
                "peak_hours": [10, 21],
                "weekend_uplift_pct": 42,
            },
            "upcoming": {
                "is_weekend_approaching": today.weekday() in [2, 3],
                "next_festival": next_festival,
                "days_to_month_end": (today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1) - today).days,
            },
        }
