"""Agent performance metrics + cost-vs-value (Phase 4, §16–17).

Aggregates AgentRun (observability) + ImpactLedger (value) to answer which agents
actually create value, with verification success rate and estimated inference cost.
ROI is informational only — never a safety-critical optimization signal.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def agent_performance(db: AsyncSession, business_id: UUID | str) -> dict[str, Any]:
    runs = await db.execute(text("""
        SELECT agent_type,
               COUNT(*) AS runs,
               COALESCE(SUM(proposals), 0) AS recommendations,
               COALESCE(SUM(auto_executed), 0) AS auto_executed,
               COALESCE(SUM(queued_for_approval), 0) AS queued_for_approval,
               COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failures,
               COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
               COALESCE(SUM(estimated_cost_usd), 0) AS cost_usd
        FROM agent_runs
        WHERE business_id = :b
        GROUP BY agent_type
        ORDER BY runs DESC
    """), {"b": str(business_id)})

    value = await db.execute(text("""
        SELECT a.agent_type,
               COALESCE(SUM(l.amount_sar), 0) AS observed_value,
               COALESCE(SUM(CASE WHEN l.verified THEN l.amount_sar ELSE 0 END), 0) AS observed_verified
        FROM impact_ledger l
        JOIN agent_actions a ON a.id = l.agent_action_id
        WHERE l.business_id = :b
        GROUP BY a.agent_type
    """), {"b": str(business_id)})
    value_by_agent = {r.agent_type: r for r in value.fetchall()}

    # Verification success rate from learned outcomes.
    verif = await db.execute(text("""
        SELECT action_type,
               COUNT(*) AS outcomes,
               COALESCE(SUM(CASE WHEN approval IN ('approved','auto_executed') AND execution_result->>'executed' = 'true' THEN 1 ELSE 0 END), 0) AS succeeded
        FROM learned_outcomes
        WHERE business_id = :b
        GROUP BY action_type
    """), {"b": str(business_id)})
    verif_by_type = {r.action_type: r for r in verif.fetchall()}

    out = []
    for r in runs.fetchall():
        v = value_by_agent.get(r.agent_type)
        observed = float(v.observed_value) if v else 0.0
        cost = float(r.cost_usd or 0)
        out.append({
            "agent_type": r.agent_type,
            "runs": r.runs,
            "recommendations": int(r.recommendations),
            "auto_executed": int(r.auto_executed),
            "queued_for_approval": int(r.queued_for_approval),
            "failures": int(r.failures),
            "avg_latency_ms": round(float(r.avg_latency_ms), 1),
            "observed_value_sar": round(observed, 2),
            "estimated_cost_usd": round(cost, 6),
            "roi_note": (
                f"value SAR {observed:,.0f} vs est. cost ${cost:.4f}"
                if cost > 0 else "deterministic (no inference cost)"
            ),
        })

    return {"agents": out, "note": "ROI is informational; observed value excludes estimates and is not used to relax safety limits."}
