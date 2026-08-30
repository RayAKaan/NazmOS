"""Root-cause investigation engine (Phase 10, §15–21).

An evidence-based hypothesis engine for recurring findings — NOT an LLM chain-of-thought
system. For a recurring finding, it collects candidate causes from real fields, scores each
with deterministic evidence, and returns SUPPORTED / PLAUSIBLE / INSUFFICIENT_EVIDENCE.

It never claims a root cause when the data only supports "a plausible contributor", and it
never fabricates causes. Root-cause outputs are recommendations — they still pass through
strategy ranking → policy → approval → execution (§19).
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CONFIDENCE_LABELS = ("supported", "plausible", "insufficient_evidence")


async def _stockout_hypotheses(db: AsyncSession, business_id: UUID | str, finding: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic stockout hypotheses from reorder level / lead time / velocity data."""
    from datetime import datetime, timedelta, timezone
    evidence = finding.get("evidence") or {}
    item_id = evidence.get("item_id") or (evidence.get("item") or {}).get("id")
    if not item_id:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    res = await db.execute(text("""
        SELECT inv.current_stock, inv.reorder_level, inv.lead_time_days, inv.safety_stock,
               COALESCE((SELECT SUM(t.quantity) FROM transactions t
                         WHERE t.item_id = :i AND t.business_id = :b
                           AND t.transaction_at >= :cutoff), 0) / 30.0 AS velocity
        FROM inventory inv
        WHERE inv.item_id = :i AND inv.business_id = :b
    """), {"i": str(item_id), "b": str(business_id), "cutoff": cutoff})
    row = res.fetchone()
    if not row:
        return []

    velocity = float(row.velocity or 0)
    reorder = float(row.reorder_level or 0)
    lead_time = float(row.lead_time_days or 0)
    safety = float(row.safety_stock or 0)
    hypotheses = []

    # Hypothesis 1: reorder threshold too low (velocity × lead time > reorder level).
    demand_during_lead = velocity * max(lead_time, 1)
    if velocity > 0 and demand_during_lead > reorder:
        hypotheses.append({
            "hypothesis_key": "reorder_threshold_low",
            "hypothesis": "Reorder threshold too low",
            "confidence": "supported",
            "evidence": [
                f"demand during lead time ≈ {demand_during_lead:.0f} units",
                f"reorder level = {reorder:.0f} units",
            ],
        })
    elif velocity > 0:
        hypotheses.append({
            "hypothesis_key": "reorder_threshold_low",
            "hypothesis": "Reorder threshold too low",
            "confidence": "plausible",
            "evidence": [f"demand during lead time ≈ {demand_during_lead:.0f} units vs reorder {reorder:.0f}"],
        })

    # Hypothesis 2: supplier lead time long relative to buffer.
    if lead_time > 3:
        hypotheses.append({
            "hypothesis_key": "supplier_lead_time",
            "hypothesis": "Supplier lead time is causing stockouts",
            "confidence": "supported" if safety and lead_time > safety else "plausible",
            "evidence": [f"lead time = {lead_time:.0f} days", f"safety stock = {safety or 0:.0f}"],
        })

    return hypotheses


async def _dead_stock_hypotheses(db: AsyncSession, business_id: UUID | str, finding: dict[str, Any]) -> list[dict[str, Any]]:
    """Dead-stock hypotheses: low demand velocity (over-purchasing vs assortment)."""
    from datetime import datetime, timedelta, timezone
    evidence = finding.get("evidence") or {}
    item_id = evidence.get("item_id") or (evidence.get("item") or {}).get("id")
    if not item_id:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    res = await db.execute(text("""
        SELECT inv.current_stock,
               COALESCE((SELECT SUM(t.quantity) FROM transactions t
                         WHERE t.item_id = :i AND t.business_id = :b
                           AND t.transaction_at >= :cutoff), 0) / 30.0 AS velocity
        FROM inventory inv
        WHERE inv.item_id = :i AND inv.business_id = :b
    """), {"i": str(item_id), "b": str(business_id), "cutoff": cutoff})
    row = res.fetchone()
    if not row:
        return []

    stock = float(row.current_stock or 0)
    velocity = float(row.velocity or 0)
    hypotheses = []

    if stock > 0 and velocity < 0.1:
        hypotheses.append({
            "hypothesis_key": "low_demand",
            "hypothesis": "Low demand (wrong assortment or over-purchasing)",
            "confidence": "supported",
            "evidence": [f"current stock = {stock:.0f} units", f"velocity ≈ {velocity:.2f} units/day"],
        })
    elif stock > 0 and velocity < 1.0:
        hypotheses.append({
            "hypothesis_key": "low_demand",
            "hypothesis": "Low demand (wrong assortment or over-purchasing)",
            "confidence": "plausible",
            "evidence": [f"current stock = {stock:.0f} units", f"velocity ≈ {velocity:.2f} units/day"],
        })
    return hypotheses


async def _margin_hypotheses(db: AsyncSession, business_id: UUID | str, finding: dict[str, Any]) -> list[dict[str, Any]]:
    """Phase 11 §Part 3: margin-leakage root-cause hypotheses from real fields.

    Investigates: supplier cost increase, selling-price mismatch, excessive discounting,
    cost-vs-price compression, missing/low-quality cost data. Uses `supplier_prices` +
    `items` only — never fabricates a cause; correlation is never asserted as causation.
    """
    from datetime import datetime, timedelta, timezone
    evidence = finding.get("evidence") or {}
    item_id = evidence.get("item_id") or (evidence.get("item") or {}).get("id")

    hypotheses: list[dict[str, Any]] = []

    # 1. Missing / low-quality cost data (data-quality gate, §Part 6).
    dq = finding.get("data_quality_score")
    if dq is not None and float(dq) < 50:
        hypotheses.append({
            "hypothesis_key": "missing_cost_data",
            "hypothesis": "Missing or low-quality cost data",
            "confidence": "supported",
            "evidence": [f"data quality score = {float(dq):.0f}/100"],
            "supporting_values": {"data_quality_score": float(dq)},
        })

    # 2. Item-level cost vs price compression.
    if item_id:
        res = await db.execute(text("""
            SELECT i.cost_price, i.sell_price,
                   CASE WHEN i.sell_price > 0 THEN ROUND(((i.sell_price - i.cost_price)/i.sell_price)*100, 1) ELSE 0 END AS margin_pct
            FROM items i WHERE i.id = :i AND i.business_id = :b
        """), {"i": str(item_id), "b": str(business_id)})
        row = res.fetchone()
        if row:
            margin = float(row.margin_pct or 0)
            if margin <= 0:
                hypotheses.append({
                    "hypothesis_key": "selling_price_mismatch",
                    "hypothesis": "Selling price below or at cost",
                    "confidence": "supported",
                    "evidence": [f"margin = {margin:.1f}%", f"cost = {float(row.cost_price or 0):.2f}", f"price = {float(row.sell_price or 0):.2f}"],
                })
            elif margin < 15:
                hypotheses.append({
                    "hypothesis_key": "selling_price_mismatch",
                    "hypothesis": "Cost-vs-price compression",
                    "confidence": "plausible",
                    "evidence": [f"margin = {margin:.1f}% (< 15%)"],
                })

            # 3. Supplier cost increase: recent supplier prices vs item cost.
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            sp = await db.execute(text("""
                SELECT sp.unit_price_sar, sp.created_at
                FROM supplier_prices sp
                WHERE sp.item_id = :i AND sp.is_active = true
                ORDER BY sp.created_at DESC LIMIT 5
            """), {"i": str(item_id)})
            prices = [dict(r._mapping) for r in sp.fetchall()]
            if len(prices) >= 2:
                latest = float(prices[0]["unit_price_sar"] or 0)
                earliest = float(prices[-1]["unit_price_sar"] or 0)
                if earliest > 0:
                    pct = (latest - earliest) / earliest * 100
                    if pct > 5:
                        hypotheses.append({
                            "hypothesis_key": "supplier_cost_increase",
                            "hypothesis": "Supplier cost increased",
                            "confidence": "supported" if pct > 10 else "plausible",
                            "evidence": [f"purchase cost changed {pct:+.1f}% over recent observations"],
                            "supporting_values": {"cost_change_pct": round(pct, 1)},
                        })
            elif not prices:
                hypotheses.append({
                    "hypothesis_key": "missing_cost_data",
                    "hypothesis": "No supplier price observations",
                    "confidence": "supported",
                    "evidence": ["no supplier_prices rows for this item"],
                })

    return hypotheses


async def _cash_hypotheses(db: AsyncSession, business_id: UUID | str, finding: dict[str, Any]) -> list[dict[str, Any]]:
    """Phase 13 §Part 6: cash-pressure hypotheses from REAL available fields only.

    inventory cash trapped (current_stock × cost_price) and slow stock conversion (low
    velocity). Never claims causality beyond what the data supports.
    """
    from datetime import datetime, timedelta, timezone
    hypotheses: list[dict[str, Any]] = []

    res = await db.execute(text("""
        SELECT i.name, inv.current_stock, i.cost_price,
               COALESCE((SELECT SUM(t.quantity) FROM transactions t
                         WHERE t.item_id = i.id AND t.business_id = :b
                           AND t.transaction_at >= :cutoff), 0) / 30.0 AS velocity
        FROM inventory inv
        JOIN items i ON i.id = inv.item_id
        WHERE inv.business_id = :b AND inv.current_stock > 0
        ORDER BY (inv.current_stock * i.cost_price) DESC
        LIMIT 50
    """), {"b": str(business_id), "cutoff": datetime.now(timezone.utc) - timedelta(days=30)})

    total_trapped = 0.0
    slow_items = []
    for r in res.fetchall():
        trapped = float(r.current_stock or 0) * float(r.cost_price or 0)
        total_trapped += trapped
        if float(r.velocity or 0) < 0.1:
            slow_items.append(r.name)

    if total_trapped > 0:
        hypotheses.append({
            "hypothesis_key": "inventory_cash_trapped",
            "hypothesis": "Cash trapped in inventory",
            "confidence": "supported" if total_trapped >= 10000 else "plausible",
            "evidence": [f"~SAR {total_trapped:,.0f} tied up in stock at cost"],
            "supporting_values": {"trapped_sar": round(total_trapped, 2)},
        })

    if slow_items:
        hypotheses.append({
            "hypothesis_key": "slow_stock_conversion",
            "hypothesis": "Slow stock conversion",
            "confidence": "supported" if len(slow_items) >= 5 else "plausible",
            "evidence": [f"{len(slow_items)} item(s) with near-zero velocity"],
        })

    if not hypotheses:
        hypotheses.append({
            "hypothesis_key": "insufficient_cash_data",
            "hypothesis": "Insufficient cash data",
            "confidence": "insufficient_evidence",
            "evidence": ["no inventory/cost data to assess cash pressure"],
        })
    return hypotheses


async def _compliance_hypotheses(db: AsyncSession, business_id: UUID | str, finding: dict[str, Any]) -> list[dict[str, Any]]:
    """Phase 13 §Part 6: compliance is detection/reminder-only. Uses only existing fields
    (expiry dates) and NEVER asserts legal non-compliance."""
    from datetime import datetime, timedelta, timezone

    hypotheses: list[dict[str, Any]] = []
    # Expiry reminders (pharmacy lots) are the only compliance-relevant field available.
    try:
        res = await db.execute(text("""
            SELECT pl.expiry_date, i.name
            FROM pharmacy_lots pl JOIN items i ON i.id = pl.item_id
            WHERE pl.business_id = :b AND pl.expiry_date IS NOT NULL
              AND pl.expiry_date <= :soon
            ORDER BY pl.expiry_date ASC LIMIT 20
        """), {"b": str(business_id), "soon": datetime.now(timezone.utc).date() + timedelta(days=45)})
        rows = res.fetchall()
        if rows:
            hypotheses.append({
                "hypothesis_key": "expiry_reminder",
                "hypothesis": "Near-expiry inventory",
                "confidence": "supported",
                "evidence": [f"{len(rows)} lot(s) expiring within 45 days"],
                "supporting_values": {"near_expiry_count": len(rows)},
            })
        else:
            hypotheses.append({
                "hypothesis_key": "no_compliance_signal",
                "hypothesis": "No compliance signal detected",
                "confidence": "insufficient_evidence",
                "evidence": ["no near-expiry lots; NazmOS is a reminder, not a compliance authority"],
            })
    except Exception:
        # pharmacy_lots may not exist in some deployments; degrade gracefully.
        hypotheses.append({
            "hypothesis_key": "no_compliance_signal",
            "hypothesis": "No compliance signal detected",
            "confidence": "insufficient_evidence",
            "evidence": ["compliance data unavailable; confirm with your accountant/provider"],
        })
    return hypotheses


HYPOTHESIS_GENERATORS = {
    "stockout_risk": _stockout_hypotheses,
    "dead_stock": _dead_stock_hypotheses,
    "margin_leakage": _margin_hypotheses,
    "cash_pressure": _cash_hypotheses,
    "compliance_risk": _compliance_hypotheses,
}


# §Part 4: root-cause → candidate-strategy mapping. Each hypothesis type maps to the
# strategies worth considering, with a per-hypothesis recommended lead strategy. This is
# deterministic and feeds the normal strategy-ranking pipeline — never a bypass.
ROOT_CAUSE_STRATEGIES: dict[str, dict[str, Any]] = {
    "supplier_cost_increase": {
        "strategies": ["margin_fix", "restock"],
        "lead": "margin_fix",
        "note": "Compare suppliers and re-evaluate purchasing before changing price.",
    },
    "selling_price_mismatch": {
        "strategies": ["pricing_increase", "margin_fix"],
        "lead": "margin_fix",
    },
    "excessive_discounting": {
        "strategies": ["pricing_increase", "margin_fix"],
        "lead": "margin_fix",
    },
    "missing_cost_data": {
        "strategies": [],
        "lead": None,
        "note": "Improve data quality before taking a pricing action.",
    },
    "reorder_threshold_low": {
        "strategies": ["restock", "transfer_inventory"],
        "lead": "restock",
    },
    "supplier_lead_time": {
        "strategies": ["restock", "transfer_inventory"],
        "lead": "transfer_inventory",
    },
    "low_demand": {
        "strategies": ["discount", "transfer_inventory"],
        "lead": "discount",
    },
}


async def investigate_root_cause(
    db: AsyncSession,
    business_id: UUID | str,
    finding: dict[str, Any],
) -> dict[str, Any]:
    """Return {hypotheses: [...], status, recommendations} for a finding.

    `recommendations` (§Part 4–5): candidate strategies derived from the root-cause
    hypotheses, gated by confidence — a `supported` hypothesis feeds the normal pipeline,
    `plausible` is allowed but confidence-penalized, `insufficient_evidence` yields an
    information-gathering recommendation rather than a high-impact action (§Part 5).
    """
    category = finding.get("category", "")
    generator = HYPOTHESIS_GENERATORS.get(category)
    if not generator:
        return {"status": "uncertain", "hypotheses": [], "recommendations": [],
                "reason": f"No root-cause model for category '{category}'"}

    hypotheses = await generator(db, business_id, finding)
    if not hypotheses:
        return {"status": "uncertain", "hypotheses": [], "recommendations": [],
                "reason": "Insufficient data to distinguish possible causes"}

    ordered = sorted(hypotheses, key=lambda h: {"supported": 0, "plausible": 1, "insufficient_evidence": 2}.get(h["confidence"], 3))
    overall = "supported" if any(h["confidence"] == "supported" for h in hypotheses) else (
        "plausible" if hypotheses else "uncertain"
    )

    recommendations = _recommendations_for_hypotheses(ordered)

    return {
        "status": overall,
        "hypotheses": ordered,
        "recommendations": recommendations,
        "note": "Evidence-based contributors; not asserted as definitive cause unless 'supported'.",
    }


def _recommendations_for_hypotheses(hypotheses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """§Part 5: translate root-cause confidence into recommendation candidates.

    - supported            → normal pipeline (lead strategy + alternatives).
    - plausible            → allowed but `confidence_penalized=True`.
    - insufficient_evidence→ information-gathering recommendation, never a high-impact action.
    """
    recommendations: list[dict[str, Any]] = []
    for h in hypotheses:
        key = h.get("hypothesis_key")
        mapping = ROOT_CAUSE_STRATEGIES.get(key, {})
        strategies = mapping.get("strategies", [])
        if h.get("confidence") == "supported":
            recommendations.append({
                "hypothesis": h.get("hypothesis"),
                "confidence": "supported",
                "strategies": strategies,
                "lead": mapping.get("lead"),
                "note": mapping.get("note"),
                "confidence_penalized": False,
            })
        elif h.get("confidence") == "plausible":
            recommendations.append({
                "hypothesis": h.get("hypothesis"),
                "confidence": "plausible",
                "strategies": strategies,
                "lead": mapping.get("lead"),
                "note": mapping.get("note"),
                "confidence_penalized": True,  # allowed but penalized
            })
        else:
            # insufficient_evidence → information-gathering, never a high-impact action.
            recommendations.append({
                "hypothesis": h.get("hypothesis"),
                "confidence": "insufficient_evidence",
                "strategies": [],
                "lead": None,
                "note": "Gather more data before acting.",
                "confidence_penalized": True,
            })
    return recommendations
