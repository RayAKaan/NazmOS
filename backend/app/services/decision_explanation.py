"""Phase 5 owner-facing decision explanations.

Explanations are assembled from trusted evidence. AI prose may explain a
validated decision but never supplies financial truth.
"""
from __future__ import annotations
from typing import Any

def build_explanation(*, decision: str, evidence: dict[str, Any], ai_reasoning: str | None = None) -> dict[str, Any]:
    items=evidence.get("items", [])
    primary=items[0] if items else {}
    facts=[]
    for key,label in (("current_stock","Current stock"),("daily_velocity","Daily demand"),
                      ("confirmed_inbound_qty","Confirmed inbound"),("days_of_supply","Days of supply"),
                      ("supplier_reliability","Supplier reliability"),("margin_pct","Margin")):
        if primary.get(key) is not None: facts.append({"label":label,"value":primary[key],"source":primary.get("sku","evidence")})
    why={"REORDER":"Demand or coverage indicates replenishment is needed.",
         "TRANSFER":"Inventory can be better positioned without creating new supply.",
         "DISCOUNT":"Inventory is slow/dead and requires a recovery path.",
         "DO_NOTHING":"Available evidence does not justify changing the current state.",
         "MANUAL_REVIEW":"Evidence is insufficient for a safe automated recommendation."}.get(decision,"Recommendation requires review.")
    return {"decision":decision,"what_we_saw":facts,"why":why,
            "ai_reasoning":ai_reasoning,"financial_authority":"NazmOS deterministic financial engine"}
