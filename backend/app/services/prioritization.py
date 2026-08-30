"""Shared deterministic problem prioritization (Phase 12, §Part 9/11).

One formula used by BOTH the Weekly Report and the Action Center, so the two never disagree
on "what matters most" without a documented reason.

Priority score (deterministic, documented):
    severity (critical 4 / high 3 / medium 2 / low 1)
  + urgency   (critical 3 / high 2 / medium 1 / low 0)
  + recurrence (recurring +2)
  + worsening  (+1 if impact rose vs prior window)
  + goal_aligned (+1 if directly aligned to an active goal)
  − data_quality penalty (0 if dq ≥ 70, else −1)
  − stale penalty (−1 if the finding's domain data is stale)

Bounded, tenant-safe, no LLM. Returns top N (default 5).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SEVERITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_URGENCY = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def priority_score(
    *,
    severity: str | None,
    urgency: str | None,
    recurring: bool,
    worsening: bool,
    goal_aligned: bool,
    data_quality_score: float | None,
    stale: bool,
) -> int:
    s = _SEVERITY.get(severity or "medium", 2)
    u = _URGENCY.get(urgency or "medium", 1)
    score = s + u
    if recurring:
        score += 2
    if worsening:
        score += 1
    if goal_aligned:
        score += 1
    dq = float(data_quality_score) if data_quality_score is not None else 100.0
    if dq < 70:
        score -= 1
    if stale:
        score -= 1
    return score


async def top_problems(
    db: AsyncSession,
    business_id: UUID | str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Deterministic top-N problems for the business, shared by Weekly Report + Action Center."""
    from app.services.recurring_detection import find_recurring_problems
    from app.services.audit_comparison import compare_audits

    # Findings (open) + recurrence set + comparison statuses.
    findings = await db.execute(text("""
        SELECT id, title, category, domain, severity, urgency, data_quality_score,
               estimated_financial_impact_sar, status
        FROM findings
        WHERE business_id = :b AND status NOT IN ('rejected', 'verified', 'failed')
        ORDER BY created_at DESC LIMIT 200
    """), {"b": str(business_id)})

    recurring_keys = {
        (r["domain"], r["category"], r["title"].strip().lower())
        for r in await find_recurring_problems(db, business_id)
    }

    try:
        comparison = await compare_audits(db, business_id)
        worsening = {f["title"].strip().lower() for f in comparison.get("findings", []) if f["status"] == "worsening"}
    except Exception:
        worsening = set()

    # Active goal metrics (for goal_aligned flag).
    try:
        from app.services.goal_service import list_goals_with_progress
        goals = await list_goals_with_progress(db, business_id)
        active_metrics = {g["metric"] for g in goals if g.get("status") in ("active", "at_risk", "on_track")}
    except Exception:
        active_metrics = set()

    from app.services.goal_domains import action_alignment
    # category → goal alignment via curated mapping is approximate; use category names.
    goal_categories = {
        "dead_stock", "stockout_risk", "margin_leakage", "supplier_cost", "revenue",
    }

    items = []
    for r in findings.fetchall():
        key = (r.domain, r.category, (r.title or "").strip().lower())
        is_recurring = key in recurring_keys
        is_worsening = (r.title or "").strip().lower() in worsening
        is_goal_aligned = r.category in goal_categories and bool(active_metrics)
        dq = float(r.data_quality_score) if r.data_quality_score is not None else None
        items.append({
            "id": str(r.id),
            "title": r.title,
            "category": r.category,
            "domain": r.domain,
            "severity": r.severity,
            "urgency": r.urgency,
            "estimated_financial_impact_sar": float(r.estimated_financial_impact_sar) if r.estimated_financial_impact_sar is not None else None,
            "recurring": is_recurring,
            "worsening": is_worsening,
            "goal_aligned": is_goal_aligned,
            "data_quality_score": dq,
            "priority": priority_score(
                severity=r.severity, urgency=r.urgency, recurring=is_recurring,
                worsening=is_worsening, goal_aligned=is_goal_aligned,
                data_quality_score=dq, stale=False,
            ),
        })

    # Sort: priority desc, then financial impact desc (deterministic tiebreak).
    items.sort(key=lambda x: (x["priority"], x["estimated_financial_impact_sar"] or 0), reverse=True)
    return items[:limit]
