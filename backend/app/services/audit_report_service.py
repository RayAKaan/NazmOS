"""Merchant-facing audit report aggregation (Phase 2, brief §21).

Combines the latest audit runs, findings, and impact ledger into one merchant-friendly
report: overall health, issue counts by severity, money at risk, recoverable value, and
top opportunities — all grounded in persisted data, never fabricated.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.impact_ledger_service import total_impact


def _json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


async def build_audit_report(db: AsyncSession, business_id: UUID | str) -> dict[str, Any]:
    latest = await db.execute(text("""
        SELECT inventory_value_sar, capital_at_risk_sar, revenue_at_risk_sar,
               gross_profit_at_risk_sar, recoverable_value_low_sar, recoverable_value_high_sar,
               expected_recovery_sar, recovery_confidence, data_quality_score
        FROM money_audits
        WHERE business_id = :b
        ORDER BY created_at DESC LIMIT 1
    """), {"b": str(business_id)})
    latest_row = latest.fetchone()

    findings = await db.execute(text("""
        SELECT severity, status, estimated_financial_impact_sar, recommended_action, category, domain, title
        FROM findings
        WHERE business_id = :b AND status NOT IN ('rejected', 'failed', 'verified')
        ORDER BY
          CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
          COALESCE(estimated_financial_impact_sar, 0) DESC
    """), {"b": str(business_id)})
    rows = findings.fetchall()

    critical = high = watch = 0
    money_at_risk = 0.0
    recoverable = 0.0
    opportunities: dict[str, float] = {}
    for r in rows:
        sev = r.severity
        if sev == "critical":
            critical += 1
        elif sev == "high":
            high += 1
        else:
            watch += 1
        impact = float(r.estimated_financial_impact_sar or 0)
        money_at_risk += impact
        rec = _json(r.recommended_action) or {}
        # "recoverable" = findings whose recommended action is a recovery-type (not a
        # review-only observation). A conservative, explicit estimate.
        if rec.get("type") in ("discount", "margin_fix", "recovery_match", "transfer_inventory", "restock_request"):
            recoverable += impact
        opportunities[r.category or r.domain] = opportunities.get(r.category or r.domain, 0.0) + impact

    # Health score: 100 − severity-weighted penalty (capped, floor 0).
    penalty = critical * 12 + high * 6 + watch * 2
    health = max(0, 100 - penalty)

    impact = await total_impact(db, business_id)

    top = sorted(opportunities.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "overall_health": health,
        "issues_found": len(rows),
        "critical": critical,
        "important": high,
        "watch": watch,
        "money_at_risk_sar": round(float(latest_row.capital_at_risk_sar or 0) if latest_row else money_at_risk, 2),
        "inventory_value_sar": round(float(latest_row.inventory_value_sar or 0), 2) if latest_row else 0.0,
        "capital_at_risk_sar": round(float(latest_row.capital_at_risk_sar or 0), 2) if latest_row else 0.0,
        "revenue_at_risk_sar": round(float(latest_row.revenue_at_risk_sar or 0), 2) if latest_row else 0.0,
        "gross_profit_at_risk_sar": round(float(latest_row.gross_profit_at_risk_sar or 0), 2) if latest_row else 0.0,
        "recoverable_value_low_sar": round(float(latest_row.recoverable_value_low_sar or 0), 2) if latest_row else 0.0,
        "recoverable_value_high_sar": round(float(latest_row.recoverable_value_high_sar or 0), 2) if latest_row else round(recoverable, 2),
        "expected_recovery_sar": float(latest_row.expected_recovery_sar) if latest_row and latest_row.expected_recovery_sar is not None else None,
        "recovery_confidence": latest_row.recovery_confidence if latest_row else "INSUFFICIENT DATA",
        "data_quality_score": float(latest_row.data_quality_score or 0) if latest_row else 0.0,
        "potential_recoverable_sar": round(float(latest_row.recoverable_value_high_sar or 0) if latest_row else recoverable, 2),
        "top_opportunities": [{"category": k, "impact_sar": round(v, 2)} for k, v in top],
        "impact": impact,
        "note": "Recoverable value is an estimate derived from findings with a recovery-type recommended action; it is not realized revenue.",
    }
