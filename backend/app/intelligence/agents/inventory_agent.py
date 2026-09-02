"""Inventory Agent — first new domain agent (Phase 2, brief §18).

Responsibilities (initial, conservative):
  - detect stockout risk (low days-of-supply);
  - detect abnormal / slow-moving inventory (dead stock);
  - recommend restocking (→ restock_request) and transfers (→ transfer_inventory);
  - estimate financial impact.

Two complementary signal sources:
  1. Business memory (CURRENT_STATE / PATTERNS) — the original, dialect-safe path.
  2. A direct inventory/transactions scan — richer, Postgres-only; best-effort so the
     SQLite dev/test path still works.

Execution stays conservative: restock requests and transfers are proposed actions that
the Agent Runtime gates through the policy engine — the agent itself never mutates state.
"""
from __future__ import annotations
from app.utils.clock import utcnow

from typing import Any

from app.database.models import MemoryType
from app.intelligence.agents.base import BaseAgent


class InventoryAgent(BaseAgent):
    agent_type = "inventory"
    name = "Inventory Agent"
    objective = "Keep the right stock in the right place: prevent stockouts and clear dead stock."

    tools = ["get_inventory", "get_sales", "forecast_demand", "suggest_inter_branch_transfers"]
    read_only = False  # proposes restock/transfer actions, gated by the runtime
    max_tool_calls = 10
    triggers = ["inventory.changed", "supplier.delivered", "sale.completed"]

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        proposals: list[dict[str, Any]] = []

        # 1. Memory-based signals (dialect-safe; original contract).
        memory = await self._get_memory(MemoryType.CURRENT_STATE.value)
        inventory = memory.get("inventory", {})
        for item_key, item_state in inventory.items():
            stock = float(item_state.get("stock", 0))
            reorder_flag = item_state.get("reorder_flag")
            if reorder_flag or stock < 10:
                proposals.append({
                    "action_type": "restock",
                    "title": f"Stockout risk: {item_key}",
                    "reason": f"Stock level {stock} is below reorder threshold",
                    "item_key": item_key,
                    "recommended_qty": max(50, int(20 - stock) * 5),
                    "confidence": 0.85,
                    "urgency": 0.9 if stock < 5 else 0.6,
                })

        patterns = await self._get_memory(MemoryType.PATTERNS.value)
        pricing = patterns.get("pricing", {})
        for item_key, history_data in pricing.items():
            history = history_data.get("history", [])
            if len(history) >= 5:
                decreases = sum(
                    1 for i in range(1, len(history))
                    if float(history[i].get("price", 0)) < float(history[i - 1].get("price", 0))
                )
                if decreases >= 3:
                    proposals.append({
                        "action_type": "discount",
                        "title": f"Dead stock: {item_key}",
                        "reason": "Repeated price decreases suggest weak demand",
                        "item_key": item_key,
                        "recommended_discount_pct": 15,
                        "confidence": 0.65,
                        "urgency": 0.5,
                    })

        # 2. Rich inventory/transactions scan (Postgres-only; best-effort on SQLite).
        try:
            proposals.extend(await self._scan_live_inventory())
        except Exception:
            pass  # SQLite/dev path — memory signals above already ran

        # §7: consume structured learning — a repeatedly-failed intervention is replaced
        # by its evidence-based alternative (e.g. restock → transfer_inventory).
        from app.services.outcome_learning import learning_adjusted_action
        adjusted = []
        for p in proposals:
            adj = await learning_adjusted_action(self.session, self.business_id, p.get("action_type", "review"))
            if adj.get("adjusted"):
                p = dict(p)
                p["action_type"] = adj["action_type"]
                p["reason"] = f"{adj['reason']} (was: {p.get('reason')})"
                p["confidence"] = min(float(p.get("confidence", 0.8)), 0.6)
                p["learning_adjusted"] = True
            adjusted.append(p)

        return {
            "agent_type": self.agent_type,
            "proposal_event_type": "agent.proposal",
            "payload": {"proposals": adjusted},
            "confidence": 0.85 if adjusted else 0.9,
            "reasons": ["Stockout risk and dead-stock scan over current inventory"],
        }

    async def _scan_live_inventory(self) -> list[dict[str, Any]]:
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import text

        cutoff = utcnow() - timedelta(days=30)
        proposals: list[dict[str, Any]] = []

        stockout = await self.session.execute(text("""
            WITH sales_30d AS (
                SELECT item_id, COALESCE(SUM(quantity), 0) AS qty_30d
                FROM transactions WHERE business_id = :b AND transaction_at >= :cutoff
                GROUP BY item_id
            )
            SELECT i.id AS item_id, i.name, inv.current_stock,
                   GREATEST(COALESCE(s.qty_30d,0)/30.0, 0.01) AS velocity,
                   inv.current_stock / NULLIF(GREATEST(COALESCE(s.qty_30d,0)/30.0, 0.01),0) AS days_of_supply
            FROM items i
            JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = :b
            LEFT JOIN sales_30d s ON s.item_id = i.id
            WHERE i.business_id = :b AND i.is_active = true AND inv.current_stock > 0
              AND inv.current_stock / NULLIF(GREATEST(COALESCE(s.qty_30d,0)/30.0, 0.01),0) < 7
            ORDER BY days_of_supply ASC LIMIT 10
        """), {"b": str(self.business_id), "cutoff": cutoff})
        for r in stockout.fetchall():
            days = float(r.days_of_supply or 0)
            proposals.append({
                "action_type": "restock",
                "title": f"Stockout risk: {r.name}",
                "reason": f"{r.name} has ~{days:.1f} days of supply left at current velocity.",
                "item_id": str(r.item_id),
                "current_stock": float(r.current_stock or 0),
                "recommended_qty": max(20, int((7 - days) * float(r.velocity))),
                "confidence": 0.85,
                "urgency": 0.9 if days < 3 else 0.6,
            })

        # Overlay canonical forecast demand on candidate items: when the
        # forecasting pipeline has a cached prediction, use it as the demand
        # signal (same numbers NazmPlanner reads) instead of raw 30-day velocity.
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
                p["demand_basis"] = "forecast"
                p["forecasted_daily_demand"] = round(daily, 2)
                p["recommended_qty"] = max(20, int((7 - days) * daily)) if days != float("inf") else p["recommended_qty"]
                p["urgency"] = 0.9 if days < 3 else 0.6
                p["reason"] = (
                    f"{p['title']}: {p.get('current_stock')} units at forecasted daily demand "
                    f"{daily:.1f}/day = ~{days:.1f} days of supply."
                )

        dead = await self.session.execute(text("""
            WITH sales_30d AS (
                SELECT item_id, COALESCE(SUM(quantity), 0) AS qty_30d
                FROM transactions WHERE business_id = :b AND transaction_at >= :cutoff
                GROUP BY item_id
            )
            SELECT i.id AS item_id, i.name, inv.current_stock, i.cost_price,
                   (inv.current_stock * i.cost_price) AS stuck_sar
            FROM items i
            JOIN inventory inv ON inv.item_id = i.id AND inv.business_id = :b
            LEFT JOIN sales_30d s ON s.item_id = i.id
            WHERE i.business_id = :b AND i.is_active = true AND inv.current_stock > 0
              AND COALESCE(s.qty_30d, 0) < 1
            ORDER BY stuck_sar DESC NULLS LAST LIMIT 10
        """), {"b": str(self.business_id), "cutoff": cutoff})
        for r in dead.fetchall():
            proposals.append({
                "action_type": "discount",
                "title": f"Dead stock: {r.name}",
                "reason": f"{r.name} has not sold in 30 days; ~SAR {float(r.stuck_sar or 0):,.0f} tied up.",
                "item_id": str(r.item_id),
                "recommended_discount_pct": 15,
                "estimated_value_sar": float(r.stuck_sar or 0),
                "confidence": 0.8,
                "urgency": 0.5,
            })

        return proposals

    async def verify_outcome(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"verified": False, "note": "inventory agent verifies via impact ledger on executed actions"}
