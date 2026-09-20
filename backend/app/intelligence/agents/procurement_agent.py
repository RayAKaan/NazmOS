"""Procurement Agent — read/plan first (Phase 2, brief §19).

Observe → compare → recommend → approval. It reasons over demand, current stock,
supplier price, lead time, and minimum order quantity — but NEVER negotiates or
communicates with suppliers, and never executes a purchase directly. Its only
outputs are `restock_request` proposals (medium risk → owner approval by default).
"""
from __future__ import annotations

from typing import Any

from app.intelligence.agents.base import BaseAgent
from app.services.audit_core import coverage_aware_daily_velocity


class ProcurementAgent(BaseAgent):
    agent_type = "procurement"
    name = "Procurement Agent"
    objective = "Recommend cost-effective restocking without ever spending money autonomously."

    tools = ["get_inventory", "get_supplier", "get_supplier_prices", "forecast_demand", "get_sales"]
    read_only = True  # procurement is read/plan only in Phase 2 — no direct purchasing
    max_tool_calls = 10
    triggers = ["supplier.delivered", "inventory.changed", "price.updated"]

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        proposals: list[dict[str, Any]] = []

        # Items approaching reorder point, joined with cheapest observed supplier price.
        res = await self.session.execute(text("""
            WITH sales_30d AS (
                SELECT item_id, COALESCE(SUM(quantity), 0) AS qty_30d
                FROM transactions WHERE business_id = :b AND transaction_at >= NOW() - INTERVAL '30 days'
                GROUP BY item_id
            ),
            lowest_price AS (
                SELECT DISTINCT ON (sp.item_id) sp.item_id, sp.unit_price_sar, s.lead_time_days, s.min_order_sar
                FROM supplier_prices sp
                JOIN suppliers s ON s.id = sp.supplier_id
                WHERE sp.is_active = true
                ORDER BY sp.item_id, sp.unit_price_sar ASC
            )
            SELECT i.id AS item_id, i.name, inv.current_stock, inv.reorder_level, s.qty_30d
            FROM items i
            JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = :b
            LEFT JOIN sales_30d s ON s.item_id = i.id
            LEFT JOIN lowest_price lp ON lp.item_id = i.id
            WHERE i.business_id = :b AND i.is_active = true
        """), {"b": str(self.business_id)})
        rows = res.fetchall()

        for r in rows:
            qty_30d = r.qty_30d
            daily_velocity = max(
                coverage_aware_daily_velocity(qty_30d, None),
                Decimal("0.01"),
            )
            days_of_supply = (
                float(r.current_stock) / float(daily_velocity) if daily_velocity > 0 else None
            )
            if days_of_supply is None or days_of_supply >= 10:
                continue
            days = float(days_of_supply)
            qty = max(20, int((14 - days) * float(daily_velocity)))
            unit_cost = float(r.unit_price_sar or 0)

        # Overlay canonical forecast demand (same numbers NazmPlanner reads)
        # onto the recommended quantity, replacing the raw velocity surrogate.
        candidate_ids = [str(p["item_id"]) for p in proposals if p.get("item_id")]
        if candidate_ids:
            from app.services.forecasting.cache import read_forecasts_batch
            from app.services.forecasting.agent_helpers import days_of_supply, forecast_daily_demand

            cached = await read_forecasts_batch(self.session, self.business_id, candidate_ids)
            for p in proposals:
                fc = cached.get(p["item_id"])
                if not fc:
                    continue
                daily = forecast_daily_demand(fc)
                if daily <= 0:
                    continue
                days = days_of_supply(float(p.get("current_stock") or 0), daily)
                if days == float("inf"):
                    continue
                qty = max(20, int((14 - days) * daily))
                total = round(qty * float(p.get("unit_price_sar") or 0), 2)
                p["demand_basis"] = "forecast"
                p["forecasted_daily_demand"] = round(daily, 2)
                p["recommended_qty"] = qty
                p["estimated_value_sar"] = total
                p["urgency"] = 0.7 if days < 5 else 0.4
                p["reason"] = (
                    f"{p['title'].replace('Procurement: ', '')} has ~{days:.1f} days of supply at "
                    f"forecasted daily demand {daily:.1f}/day. Recommend ordering ~{qty} units "
                    f"(SAR {float(p.get('unit_price_sar') or 0):.2f}/unit)."
                )

        # §8: consume learning + supplier reliability. Repeatedly-failed restocks are
        # replaced by their alternative; rejection history for restocking is surfaced as an
        # explicit caveat (only claims supported by actual data).
        from app.services.outcome_learning import learning_adjusted_action, rejections_for
        adjusted = []
        rejections = await rejections_for(self.session, self.business_id, action_type="restock")
        rejected_reason = rejections[0]["rejection_reason"] if rejections else None

        for p in proposals:
            adj = await learning_adjusted_action(self.session, self.business_id, p.get("action_type", "restock"))
            if adj.get("adjusted"):
                p = dict(p)
                p["action_type"] = adj["action_type"]
                p["reason"] = f"{adj['reason']} (was: {p.get('reason')})"
                p["confidence"] = min(float(p.get("confidence", 0.7)), 0.6)
                p["learning_adjusted"] = True
            elif rejected_reason:
                p = dict(p)
                p["reason"] = f"{p.get('reason')} Note: owner previously rejected restocking ({rejected_reason})."
                p["confidence"] = min(float(p.get("confidence", 0.7)), 0.55)
            adjusted.append(p)

        return {
            "agent_type": self.agent_type,
            "proposal_event_type": "agent.proposal",
            "payload": {"proposals": adjusted},
            "confidence": 0.8 if adjusted else 0.9,
            "reasons": ["Reorder-point + supplier-price scan (read/plan only)"],
        }

    async def verify_outcome(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"verified": False, "note": "procurement is read/plan only; no side effects to verify"}
