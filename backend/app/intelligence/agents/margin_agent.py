"""Margin Agent — price/cost change detection (Phase 3, brief §10).

Focus: price/cost changes, discount leakage, margin deterioration, and profitable-product
opportunities. Read/plan only — it proposes `margin_fix` actions (medium risk → owner
approval) and never mutates state directly.

It uses the live PostgreSQL ledger (items.cost_price / sell_price / margin) — the actual
source of truth — not the memory snapshot, so its signals are always current.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.intelligence.agents.base import BaseAgent


class MarginAgent(BaseAgent):
    agent_type = "margin"
    name = "Margin Agent"
    objective = "Protect and grow margin by surfacing price/cost changes and discount leakage."

    tools = ["get_inventory", "get_sales", "get_supplier_prices"]
    read_only = False  # proposes margin_fix actions, gated by the runtime
    max_tool_calls = 8
    triggers = ["price.updated", "supplier_price.changed"]

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        proposals: list[dict[str, Any]] = []

        # Thin-margin products: sell_price barely above cost, or margin eroded.
        res = await self.session.execute(text("""
            SELECT i.id AS item_id, i.name, i.cost_price, i.sell_price,
                   CASE WHEN i.sell_price > 0
                        THEN ROUND(((i.sell_price - i.cost_price) / i.sell_price) * 100, 1)
                        ELSE 0 END AS margin_pct
            FROM items i
            WHERE i.business_id = :b AND i.is_active = true
              AND i.cost_price > 0 AND i.sell_price > 0
              AND (i.sell_price - i.cost_price) / NULLIF(i.sell_price, 0) < 0.15
            ORDER BY margin_pct ASC
            LIMIT 10
        """), {"b": str(self.business_id)})
        for r in res.fetchall():
            margin = float(r.margin_pct or 0)
            proposals.append({
                "action_type": "margin_fix",
                "title": f"Thin margin: {r.name}",
                "reason": f"{r.name} margin is {margin:.1f}% (cost SAR {float(r.cost_price or 0):,.2f}, price SAR {float(r.sell_price or 0):,.2f}).",
                "item_id": str(r.item_id),
                "current_margin_pct": margin,
                "confidence": 0.75,
                "urgency": 0.7 if margin < 5 else 0.4,
            })

        return {
            "agent_type": self.agent_type,
            "proposal_event_type": "agent.proposal",
            "payload": {"proposals": proposals},
            "confidence": 0.8 if proposals else 0.9,
            "reasons": ["Thin-margin scan over the live product ledger"],
        }

    async def verify_outcome(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"verified": False, "note": "margin agent verifies via impact ledger on executed actions"}
