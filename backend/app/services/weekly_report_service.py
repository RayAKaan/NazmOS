"""Weekly Money Report + explainable Business Health score (Phase 3, §17–18).

Builds the merchant-facing weekly report from the Impact Ledger, findings, and agent
actions — always separating OBSERVED impact from ESTIMATED impact (never turning
estimates into claimed realized revenue).

Health score is broken into traceable dimensions (inventory / margins / procurement /
cash / sales / compliance), each derived from findings/data — not a mystery AI number.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.impact_ledger_service import total_impact

# Finding domain → health dimension (each score is traceable to findings).
DOMAIN_DIMENSION = {
    "money_audit": "margins",
    "inventory": "inventory",
    "recovery_match": "inventory",
    "compliance": "compliance",
    "procurement": "procurement",
    "cash": "cash",
    "sales": "sales",
}

DIMENSIONS = ["inventory", "margins", "procurement", "cash", "sales", "compliance", "operations"]


def _json(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return v
    if v is None:
        return None
    try:
        return json.loads(v)
    except Exception:
        return v


async def health_trend(db: AsyncSession, business_id: UUID | str) -> dict[str, Any]:
    """Trend-based health: current score vs the previous 7-day window's score (§24)."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    async def _score(since: datetime, until: datetime) -> dict[str, Any]:
        rows = await db.execute(text("""
            SELECT domain, severity, COUNT(*) AS n
            FROM findings
            WHERE business_id = :b AND created_at >= :since AND created_at < :until
              AND status NOT IN ('rejected', 'failed', 'verified')
            GROUP BY domain, severity
        """), {"b": str(business_id), "since": since, "until": until})
        weight = {"critical": 12, "high": 6, "medium": 2, "low": 0, "info": 0}
        penalty = 0
        for r in rows.fetchall():
            penalty += weight.get(r.severity, 0) * int(r.n)
        return {"overall_health": max(0, 100 - penalty)}

    current = await _score(week_ago, now)
    previous = await _score(two_weeks_ago, week_ago)
    delta = current["overall_health"] - previous["overall_health"]

    return {
        "current_health": current["overall_health"],
        "previous_health": previous["overall_health"],
        "trend": "up" if delta > 0 else "down" if delta < 0 else "flat",
        "delta": delta,
        "note": "Health is derived from finding severity within each window; every score is traceable to findings.",
    }


async def health_score_breakdown(db: AsyncSession, business_id: UUID | str) -> dict[str, Any]:
    """Explainable health score: 100 − severity-weighted penalties, broken down by
    dimension, each traceable to findings."""
    rows = await db.execute(text("""
        SELECT domain, severity, COUNT(*) AS n
        FROM findings
        WHERE business_id = :b AND status NOT IN ('rejected', 'failed', 'verified')
        GROUP BY domain, severity
    """), {"b": str(business_id)})
    weight = {"critical": 12, "high": 6, "medium": 2, "low": 0, "info": 0}

    dim_penalty = {d: 0 for d in DIMENSIONS}
    dim_counts = {d: 0 for d in DIMENSIONS}
    for r in rows.fetchall():
        dim = DOMAIN_DIMENSION.get(r.domain, "operations")
        w = weight.get(r.severity, 0)
        dim_penalty[dim] += w * int(r.n)
        dim_counts[dim] += int(r.n)

    total_penalty = sum(dim_penalty.values())
    overall = max(0, 100 - total_penalty)

    dimensions = []
    for d in DIMENSIONS:
        dimensions.append({
            "dimension": d,
            "score": max(0, 100 - dim_penalty[d]),
            "findings": dim_counts[d],
        })

    return {"overall_health": overall, "dimensions": dimensions}


async def build_weekly_report(db: AsyncSession, business_id: UUID | str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    impact = await total_impact(db, business_id)

    # Recurring problems (§23).
    from app.services.recurring_detection import find_recurring_problems
    recurring = await find_recurring_problems(db, business_id)

    # Phase 12 §Part 9: shared deterministic top-N prioritization.
    from app.services.prioritization import top_problems
    priorities = await top_problems(db, business_id, limit=5)

    # Observed vs estimated already separated by total_impact.
    top_findings = await db.execute(text("""
        SELECT title, severity, domain, estimated_financial_impact_sar
        FROM findings
        WHERE business_id = :b AND created_at >= :since
          AND status NOT IN ('rejected')
        ORDER BY estimated_financial_impact_sar DESC NULLS LAST LIMIT 5
    """), {"b": str(business_id), "since": week_ago})
    findings = [dict(r._mapping) for r in top_findings.fetchall()]

    top_actions = await db.execute(text("""
        SELECT title, action_type, status, created_at
        FROM agent_actions
        WHERE business_id = :b AND created_at >= :since
        ORDER BY created_at DESC LIMIT 5
    """), {"b": str(business_id), "since": week_ago})
    actions = [dict(r._mapping) for r in top_actions.fetchall()]

    pending = await db.execute(text("""
        SELECT COUNT(*) FROM agent_actions
        WHERE business_id = :b AND status = 'pending_approval'
    """), {"b": str(business_id)})

    unresolved = await db.execute(text("""
        SELECT COUNT(*) FROM findings
        WHERE business_id = :b AND status NOT IN ('verified', 'rejected', 'failed')
    """), {"b": str(business_id)})

    health = await health_score_breakdown(db, business_id)

    return {
        "period": {"from": week_ago.isoformat(), "to": now.isoformat()},
        "title": "NazmOS Weekly Report",
        "impact": impact,  # observed_sar vs estimated_sar kept distinct
        "health": health,
        "top_findings": findings,
        "top_actions_completed": actions,
        "pending_approvals": int(pending.scalar() or 0),
        "unresolved_issues": int(unresolved.scalar() or 0),
        "recurring_problems": recurring,
        "priorities": priorities,
        "note": "Observed impact is measured from business data; estimated impact is a projection and is never presented as realized revenue.",
    }
