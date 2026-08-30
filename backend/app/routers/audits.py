"""Audit Engine + Findings API (Phase 1).

Read-oriented surface for the Action Center: list audit runs, list/advance/verify
findings, and manually trigger an audit run for a domain. All mutating paths go
through the same tenant-access guard as every other router.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.services import audit_engine, finding_service, tool_registry
from app.services.impact_ledger_service import total_impact, list_ledger
from app.services.audit_report_service import build_audit_report
from app.services.weekly_report_service import build_weekly_report, health_score_breakdown, health_trend
from app.services.orchestrator import run_orchestrator
from app.services.supplier_price_ingestion import ingest_from_purchase_order
from app.services.goal_service import (
    create_goal, list_goals_with_progress, goal_history, enrich_trajectory,
    snapshot_goal_progress, estimate_miss_days, goal_alignment_chain,
)
from app.services.outcome_learning import learn_from_action, list_learned_outcomes, rejections_for, intervention_effectiveness
from app.services.agent_performance import agent_performance
from app.services.recurring_detection import find_recurring_problems
from app.services.graph_context import finding_graph_context, product_graph_context
from app.services.audit_comparison import compare_audits
from app.services.finding_timeline import build_finding_timeline
from app.services.goal_domains import list_goal_types

router = APIRouter(prefix="/api/v1/audits", tags=["Audit Engine"])


@router.get("/domains")
async def list_domains(current_user: User = Depends(get_current_user)):
    """Available audit domains."""
    return {"domains": audit_engine.list_domains()}


@router.post("/run")
async def run_audit_endpoint(
    business_id: UUID,
    domain: str = Query(..., description="audit domain name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually run an audit domain for a business (brief §11: manual trigger)."""
    await assert_business_access(db, business_id, current_user)
    if domain not in audit_engine.AUDIT_DOMAINS:
        raise HTTPException(400, f"Unknown domain '{domain}'. Known: {audit_engine.list_domains()}")
    return await audit_engine.run_audit(db, business_id, domain, trigger="manual")


@router.get("/runs")
async def list_runs(
    business_id: UUID,
    domain: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    params = {"b": str(business_id), "lim": limit}
    domain_clause = ""
    if domain:
        domain_clause = "AND domain = :domain"
        params["domain"] = domain
    res = await db.execute(text(f"""
        SELECT id, domain, status, trigger, trigger_event_type, started_at, completed_at, summary, error, created_at
        FROM audit_runs
        WHERE business_id = :b {domain_clause}
        ORDER BY created_at DESC LIMIT :lim
    """), params)
    return {"runs": [dict(r._mapping) | {"id": str(r.id)} for r in res.fetchall()]}


@router.get("/findings")
async def list_findings_endpoint(
    business_id: UUID,
    status: str | None = None,
    domain: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    findings = await finding_service.list_findings(db, business_id, status=status, domain=domain, limit=limit)
    return {"findings": findings, "count": len(findings)}


class AdvanceStatusRequest(BaseModel):
    finding_id: UUID
    to_status: str = Field(..., description="target status")


@router.post("/findings/status")
async def advance_finding_status(
    request: AdvanceStatusRequest,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    result = await finding_service.advance_status(db, request.finding_id, request.to_status)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "Status advance failed"))
    return result


class VerifyRequest(BaseModel):
    finding_id: UUID
    verified: bool
    actual_impact_sar: float | None = None
    note: str | None = None


@router.post("/findings/verify")
async def verify_finding_endpoint(
    request: VerifyRequest,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    result = await finding_service.verify_finding(
        db, request.finding_id, request.verified, request.actual_impact_sar, request.note
    )
    if not result.get("ok"):
        raise HTTPException(404, result.get("reason", "Verification failed"))
    return result


@router.get("/tools")
async def list_tools(current_user: User = Depends(get_current_user)):
    """List the tools the Agent Runtime can call (brief §7)."""
    return {"tools": tool_registry.list_tools()}


@router.get("/findings/{finding_id}")
async def get_finding_detail(
    finding_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full finding detail — the product's trust layer (§20)."""
    await assert_business_access(db, business_id, current_user)
    finding = await finding_service.get_finding(db, finding_id, business_id)
    if not finding:
        raise HTTPException(404, "Finding not found for this business")
    return finding


@router.get("/report")
async def audit_report(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Merchant-friendly audit report (§21)."""
    await assert_business_access(db, business_id, current_user)
    return await build_audit_report(db, business_id)


@router.get("/impact")
async def impact_summary(
    business_id: UUID,
    observed_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Impact ledger summary (observed + estimated) for the Dashboard IMPACT section (§11)."""
    await assert_business_access(db, business_id, current_user)
    return await total_impact(db, business_id, observed_only=observed_only)


@router.get("/impact/entries")
async def impact_entries(
    business_id: UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    return {"entries": await list_ledger(db, business_id, limit=limit)}


@router.get("/weekly-report")
async def weekly_report(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Weekly Money Report from the Impact Ledger (§17)."""
    await assert_business_access(db, business_id, current_user)
    return await build_weekly_report(db, business_id)


@router.get("/health")
async def health_score(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explainable business health score, broken down by dimension (§18)."""
    await assert_business_access(db, business_id, current_user)
    return await health_score_breakdown(db, business_id)


@router.post("/orchestrate")
async def orchestrate(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run the Orchestrator: collect domain-agent recommendations into a unified plan (§12)."""
    await assert_business_access(db, business_id, current_user)
    result = await run_orchestrator(db, business_id)
    return {
        "goals": result.goals,
        "domain_results": result.domain_results,
        "plan": result.plan,
        "pending_approval": result.pending_approval,
        "auto_executed": result.auto_executed,
    }


# ── Phase 4: goals, learning, performance, graph context ──────────────────

class GoalCreate(BaseModel):
    title: str
    metric: str
    direction: str = Field(default="decrease", pattern="^(decrease|increase|maintain)$")
    target: float
    baseline: float | None = None
    deadline: str | None = None
    priority: int = Field(default=3, ge=1, le=5)
    source: str = Field(default="impact_ledger")
    source_key: str | None = None


@router.get("/goals")
async def list_goals(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Structured business goals with deterministic progress (§2–3)."""
    await assert_business_access(db, business_id, current_user)
    return {"goals": await list_goals_with_progress(db, business_id)}


@router.post("/goals")
async def create_goal_endpoint(
    business_id: UUID,
    body: GoalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    from datetime import date
    deadline = date.fromisoformat(body.deadline) if body.deadline else None
    goal_id = await create_goal(
        db, business_id, title=body.title, metric=body.metric, direction=body.direction,
        target=body.target, baseline=body.baseline, deadline=deadline, priority=body.priority,
        source=body.source, source_key=body.source_key,
    )
    return {"goal_id": str(goal_id)}


@router.get("/learning/outcomes")
async def list_outcomes(
    business_id: UUID,
    kind: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Structured learned outcomes (fact/inference/preference/hypothesis) (§5–8)."""
    await assert_business_access(db, business_id, current_user)
    return {"outcomes": await list_learned_outcomes(db, business_id, kind=kind, limit=limit)}


@router.get("/learning/rejections")
async def list_rejections(
    business_id: UUID,
    action_type: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rejection evidence for future agents (§6)."""
    await assert_business_access(db, business_id, current_user)
    return {"rejections": await rejections_for(db, business_id, action_type=action_type, limit=limit)}


@router.post("/learning/from-action")
async def learn_endpoint(
    business_id: UUID,
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Distill an executed/rejected action into a learned outcome (idempotent)."""
    await assert_business_access(db, business_id, current_user)
    result = await learn_from_action(db, business_id, action_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "Learning failed"))
    return result


@router.get("/performance")
async def performance(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Agent performance + cost-vs-value metrics (§16–17)."""
    await assert_business_access(db, business_id, current_user)
    return await agent_performance(db, business_id)


@router.get("/recurring-problems")
async def recurring_problems(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recurring-problem detection (§23)."""
    await assert_business_access(db, business_id, current_user)
    return {"recurring": await find_recurring_problems(db, business_id)}


@router.get("/health-trend")
async def health_trend_endpoint(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trend-based business health (§24)."""
    await assert_business_access(db, business_id, current_user)
    return await health_trend(db, business_id)


@router.get("/graph/finding/{finding_id}")
async def finding_graph(
    finding_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Connected graph context for a finding (§10) — tenant-scoped."""
    await assert_business_access(db, business_id, current_user)
    return await finding_graph_context(db, business_id, finding_id)


@router.get("/graph/product/{item_id}")
async def product_graph(
    item_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    return await product_graph_context(db, business_id, item_id)


# ── Phase 5: goal history, audit comparison, learning effectiveness ───────

@router.get("/goals/{goal_id}/history")
async def goal_history_endpoint(
    goal_id: UUID,
    business_id: UUID,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historical progress snapshots + deterministic trajectory (§8–10)."""
    await assert_business_access(db, business_id, current_user)
    history = await goal_history(db, business_id, goal_id, limit=limit)
    return {"goal_id": str(goal_id), "history": history, **enrich_trajectory(history)}


@router.post("/goals/snapshot")
async def snapshot_goals(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually snapshot goal progress (the scheduled task does this daily, §9)."""
    await assert_business_access(db, business_id, current_user)
    return await snapshot_goal_progress(db, business_id, source="manual")


@router.get("/compare")
async def compare_endpoint(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Audit 2.0 comparison: NEW / PERSISTENT / IMPROVING / WORSENING / RESOLVED / RECURRING (§12–14)."""
    await assert_business_access(db, business_id, current_user)
    return await compare_audits(db, business_id)


@router.get("/learning/effectiveness")
async def effectiveness(
    business_id: UUID,
    action_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historical intervention effectiveness for an action type (§5/§7)."""
    await assert_business_access(db, business_id, current_user)
    return await intervention_effectiveness(db, business_id, action_type=action_type)


# ── Phase 6: goal alignment chain + deadline trajectory ───────────────────

@router.get("/goals/{goal_id}/chain")
async def goal_chain(
    goal_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Goal → findings → actions → impact → progress, fully queryable (§12)."""
    await assert_business_access(db, business_id, current_user)
    result = await goal_alignment_chain(db, business_id, goal_id)
    if not result.get("ok", True):
        raise HTTPException(404, result.get("reason", "Goal not found"))
    return result


@router.get("/goals/{goal_id}/trajectory")
async def goal_trajectory(
    goal_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deadline-based trajectory: projected miss-by-N-days (§11). Deterministic."""
    await assert_business_access(db, business_id, current_user)
    history = await goal_history(db, business_id, goal_id, limit=90)

    goal = await db.execute(text("""
        SELECT target, direction, deadline FROM business_goals WHERE id = :gid AND business_id = :b
    """), {"gid": str(goal_id), "b": str(business_id)})
    grow = goal.fetchone()
    if not grow:
        raise HTTPException(404, "Goal not found")

    current = history[-1]["measured_value"] if history else None
    from decimal import Decimal
    estimate = estimate_miss_days(
        history,
        current_value=Decimal(str(current)) if current is not None else None,
        target=Decimal(str(grow.target)),
        direction=grow.direction,
        deadline=grow.deadline,
    )
    return {
        "goal_id": str(goal_id),
        "trajectory": enrich_trajectory(history),
        "deadline_projection": estimate,
        "history": history,
    }


# ── Phase 7: finding timeline + goal-type catalogue + reconciliation ──────

@router.get("/findings/{finding_id}/timeline")
async def finding_timeline_endpoint(
    finding_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Finding decision timeline (§7) — evidence + decisions, never chain-of-thought."""
    await assert_business_access(db, business_id, current_user)
    timeline = await build_finding_timeline(db, finding_id, business_id)
    if not timeline:
        raise HTTPException(404, "Finding not found for this business")
    return {"finding_id": str(finding_id), "timeline": timeline}


@router.get("/goal-types")
async def goal_types(current_user: User = Depends(get_current_user)):
    """Curated goal-type catalogue for the goal-definition UX (§11)."""
    return {"goal_types": list_goal_types()}


@router.post("/learning/reconcile")
async def reconcile_endpoint(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually reconcile LearnedOutcome ↔ OutcomeFeedback for this business (§9)."""
    await assert_business_access(db, business_id, current_user)
    from app.services.learning_reconciliation import reconcile_all
    return await reconcile_all(db, business_id)


# ── Phase 8: strategy performance + per-finding impact attribution ────────

@router.get("/strategy-performance")
async def strategy_performance_endpoint(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read-only strategy performance summary (§11)."""
    await assert_business_access(db, business_id, current_user)
    from app.services.strategy_performance import strategy_summaries
    return {"strategies": await strategy_summaries(db, business_id)}


@router.get("/strategy-performance/{action_type}/categories")
async def strategy_categories(
    action_type: str,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Contextual strategy performance by finding category (§8)."""
    await assert_business_access(db, business_id, current_user)
    from app.services.strategy_performance import strategy_by_category
    return {"action_type": action_type, "categories": await strategy_by_category(db, business_id, action_type)}


@router.get("/findings/{finding_id}/impact")
async def finding_impact(
    finding_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-finding observed impact with attribution quality (§2/§5)."""
    await assert_business_access(db, business_id, current_user)
    from app.services.impact_ledger_service import finding_observed_impact
    return await finding_observed_impact(db, business_id, finding_id)


# ── Phase 9: explainable recommendation (why this strategy?) ──────────────

@router.get("/findings/{finding_id}/recommendation")
async def finding_recommendation(
    finding_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Structured, explainable recommendation for a finding (§14–15): selected strategy,
    alternatives, historical performance, expected impact, urgency, confidence, data
    quality, approval requirement. Evidence-based, never chain-of-thought."""
    await assert_business_access(db, business_id, current_user)
    from app.services.strategy_performance import strategy_summary, strategy_summary_recency
    from app.services.decision_scoring import compute_recommendation_score

    f = await db.execute(text("""
        SELECT id, category, severity, urgency, data_quality_score, confidence,
               estimated_financial_impact_sar, recommended_action, action_risk
        FROM findings WHERE id = :id AND business_id = :b
    """), {"id": str(finding_id), "b": str(business_id)})
    row = f.fetchone()
    if not row:
        raise HTTPException(404, "Finding not found for this business")

    rec = row.recommended_action if isinstance(row.recommended_action, dict) else (json.loads(row.recommended_action) if row.recommended_action else {})
    selected = rec.get("type") or "review"
    from app.services.goal_domains import action_alignment
    alt_types = [t for t in action_alignment(selected) or []]
    # alternatives = other action types for this finding's goal (curated mapping).
    alternatives = [t for t in ("transfer_inventory", "discount", "restock", "margin_fix", "pricing_decrease")
                    if t != selected]

    selected_strat = await strategy_summary(db, business_id, selected)
    selected_recency = await strategy_summary_recency(db, business_id, selected)
    # §11–13: recency shifts relevance, not raw evidence tier.
    scored_strategy = {
        **selected_strat,
        "effectiveness": selected_recency.get("recency_weighted_effectiveness"),
        "success_rate": selected_recency.get("recency_weighted_success_rate"),
    }
    alt_strats = []
    for t in alternatives:
        s = await strategy_summary(db, business_id, t)
        if s["attempts"] > 0:
            alt_strats.append({"action_type": t, "effectiveness": s["effectiveness"],
                               "success_rate": s["success_rate"], "evidence_tier": s["evidence_tier"],
                               "attempts": s["attempts"]})

    scored = compute_recommendation_score(
        goal_alignment="directly_aligned" if action_alignment(selected) else "unrelated",
        estimated_impact_sar=float(row.estimated_financial_impact_sar) if row.estimated_financial_impact_sar is not None else None,
        urgency=row.urgency, confidence=float(row.confidence) if row.confidence is not None else None,
        data_quality_score=float(row.data_quality_score) if row.data_quality_score is not None else None,
        strategy=scored_strategy, risk=row.action_risk,
    )

    return {
        "finding_id": str(finding_id),
        "recommended": selected,
        "alternatives": alt_strats,
        "score": scored,
        "recency": {
            "raw_success_rate": selected_strat.get("success_rate"),
            "recency_weighted_success_rate": selected_recency.get("recency_weighted_success_rate"),
            "raw_effectiveness": selected_strat.get("effectiveness"),
            "recency_weighted_effectiveness": selected_recency.get("recency_weighted_effectiveness"),
        },
    }


# ── Phase 10: root-cause investigation + operational health ───────────────

@router.get("/findings/{finding_id}/root-cause")
async def finding_root_cause(
    finding_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Evidence-based root-cause investigation for a finding (§15–21). Never asserts a
    cause unless supported; returns 'uncertain' otherwise."""
    await assert_business_access(db, business_id, current_user)
    from app.services.root_cause import investigate_root_cause

    f = await db.execute(text("""
        SELECT id, category, severity, title, evidence FROM findings
        WHERE id = :id AND business_id = :b
    """), {"id": str(finding_id), "b": str(business_id)})
    row = f.fetchone()
    if not row:
        raise HTTPException(404, "Finding not found for this business")

    finding = {
        "id": str(row.id), "category": row.category, "severity": row.severity, "title": row.title,
        "evidence": row.evidence if isinstance(row.evidence, dict) else (json.loads(row.evidence) if row.evidence else {}),
    }
    return await investigate_root_cause(db, business_id, finding)


@router.get("/operational-health")
async def operational_health_endpoint(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Operator-facing health + data freshness (§25–28)."""
    await assert_business_access(db, business_id, current_user)
    from app.services.operational_health import operational_health
    return await operational_health(db, business_id)


# ── Phase 12: shared deterministic prioritization ─────────────────────────

@router.get("/priorities")
async def priorities_endpoint(
    business_id: UUID,
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Shared deterministic top-N problems (used by both Action Center + Weekly Report)."""
    await assert_business_access(db, business_id, current_user)
    from app.services.prioritization import top_problems
    return {"priorities": await top_problems(db, business_id, limit=max(1, min(limit, 20)))}
