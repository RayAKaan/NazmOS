"""CEO / Orchestrator Agent (Phase 3, brief §11–12).

The orchestrator coordinates domain agents — it does NOT have unrestricted access and
does NOT bypass domain policies. It:
  1. understands business goals (from memory GOALS);
  2. collects structured domain proposals (each agent runs through the SAME runtime
     and policy engine as always);
  3. compares recommendations, deduplicates, and ranks by financial impact × urgency ×
     confidence × actionability;
  4. constructs a unified, human-facing action plan.

It produces structured results — never free-form agent-to-agent chat. It does NOT execute
anything itself; every candidate action still passes the policy engine via run_agent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.intelligence.agents.base import BaseAgent
from app.intelligence.agents.registry import AGENT_REGISTRY
from app.services.runtime import run_agent
from app.services.business_memory import get_memory
from app.services.goal_service import list_goals_with_progress

logger = logging.getLogger("orchestrator")

# Agents the orchestrator may delegate to. Least privilege: a curated subset, not all.
ORCHESTRATED_AGENTS = ["recovery", "inventory", "procurement", "margin"]

# Goal metric → action types that directly align (for explainable prioritization, §4).
# Phase 7 §10: superseded by the curated mapping in goal_domains.action_alignment;
# kept for backward compatibility where a raw metric string is still passed.
GOAL_ACTION_ALIGNMENT: dict[str, list[str]] = {
    "dead_stock_value": ["discount", "transfer_inventory", "recovery_match"],
    "gross_margin": ["margin_fix", "pricing_increase", "pricing_decrease"],
    "supplier_cost": ["restock", "margin_fix"],
    "stockout_risk": ["restock", "transfer_inventory"],
    "revenue": ["restock", "pricing_increase"],
}


@dataclass
class OrchestrationResult:
    goals: list[dict[str, Any]] = field(default_factory=list)
    domain_results: list[dict[str, Any]] = field(default_factory=list)
    plan: list[dict[str, Any]] = field(default_factory=list)
    pending_approval: int = 0
    auto_executed: int = 0


def _aligns_with_goal(goals: list[dict[str, Any]], action_type: str) -> str:
    """§12: return goal-alignment as directly_aligned / indirectly_relevant / unrelated.

    Uses the curated goal_domains.action_alignment where the metric is a known type;
    falls back to the legacy GOAL_ACTION_ALIGNMENT for raw metric strings.
    """
    from app.services.goal_domains import action_alignment, GOAL_TYPE_BY_KEY

    active_metrics = {g["metric"] for g in goals if g.get("status") in ("active", "at_risk", "on_track")}
    if not active_metrics:
        return "unrelated"

    for metric in active_metrics:
        if metric in GOAL_TYPE_BY_KEY:
            if metric in action_alignment(action_type):
                return "directly_aligned"
        elif action_type in GOAL_ACTION_ALIGNMENT.get(metric, []):
            return "directly_aligned"
    return "unrelated"


async def run_orchestrator(
    db: AsyncSession,
    business_id: UUID | str,
    context: dict[str, Any] | None = None,
) -> OrchestrationResult:
    """Collect domain-agent recommendations and produce a goal-aware, unified action plan."""
    result = OrchestrationResult()

    # 1. Business goals (structured, with deterministic progress).
    try:
        result.goals = await list_goals_with_progress(db, business_id)
    except Exception:
        result.goals = []

    # 2. Delegate investigations to each curated domain agent (same runtime + policy gate).
    for agent_type in ORCHESTRATED_AGENTS:
        agent_cls = AGENT_REGISTRY.get(agent_type)
        if not agent_cls:
            continue
        agent: BaseAgent = agent_cls(db, business_id)
        try:
            run = await run_agent(db, agent, context, trigger="orchestrator", record=True)
            result.domain_results.append({
                "agent_type": agent_type,
                "proposals": run.proposals,
                "auto_executed": run.auto_executed,
                "queued_for_approval": run.queued_for_approval,
                "actions": run.actions,
            })
            result.auto_executed += run.auto_executed
            result.pending_approval += run.queued_for_approval
        except Exception as exc:
            logger.warning("orchestrator: agent %s failed: %s", agent_type, exc)

    # 3. Build a unified, ranked, goal-aware action plan with a deterministic,
    # explainable decision score (§8–14). The score ranks; policy still gates (§13).
    from app.services.strategy_performance import strategy_summary
    from app.services.decision_scoring import compute_recommendation_score
    plan = []
    for dr in result.domain_results:
        for action in dr.get("actions", []):
            if action.get("status") in ("pending_approval", "auto_executed"):
                alignment = _aligns_with_goal(result.goals, action.get("action_type", ""))
                strat = await strategy_summary(db, business_id, action.get("action_type", ""))
                scored = compute_recommendation_score(
                    goal_alignment=alignment,
                    estimated_impact_sar=action.get("estimated_value_sar"),
                    urgency=action.get("urgency"),
                    confidence=action.get("confidence"),
                    data_quality_score=action.get("data_quality_score"),
                    strategy=strat,
                    risk=action.get("risk"),
                )
                plan.append({
                    "agent": dr["agent_type"],
                    "action_id": action.get("action_id"),
                    "action_type": action.get("action_type"),
                    "risk": action.get("risk"),
                    "decision": action.get("decision"),
                    "reason": action.get("reason"),
                    "goal_alignment": alignment,
                    "goal_aligned": alignment == "directly_aligned",
                    "approval_required": action.get("decision") != "auto",
                    "dependencies": [],
                    "strategy_success_rate": strat.get("success_rate"),
                    "strategy_effectiveness": strat.get("effectiveness"),
                    "strategy_evidence_tier": strat.get("evidence_tier"),
                    "score": scored["score"],
                    "explanation": scored["explanation"],
                })

    # Rank by decision score, then decision state (auto first within similar scores).
    def sort_key(a):
        return (
            {"auto": 0, "draft": 1, "approve": 2}.get(a.get("decision"), 2),
            -1.0 * (a.get("score") or 0.0),
        )
    plan.sort(key=sort_key)
    result.plan = plan

    return result
