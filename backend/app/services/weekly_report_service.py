"""Weekly Money Report + explainable Business Health score (Phase 3, §17–18).

Builds the merchant-facing weekly report from the Impact Ledger, findings, and agent
actions — always separating OBSERVED impact from ESTIMATED impact (never turning
estimates into claimed realized revenue).

Health score is the ``findings_health`` metric (severity-penalty-based); the
dashboard uses the distinct ``inventory_health`` metric.  Both live in
``health_metrics`` and carry a ``metric`` key so consumers label them correctly.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.impact_ledger_service import total_impact

# Canonical definitions live in health_metrics; re-export for backward compat
# (audits router, test_phase3).
from app.services.health_metrics import (  # noqa: F401
    DOMAIN_DIMENSION,
    DIMENSIONS,
    findings_health_breakdown as health_score_breakdown,
    findings_health_trend as health_trend,
)


def _json(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return v
    if v is None:
        return None
    try:
        return json.loads(v)
    except Exception:
        return v


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
