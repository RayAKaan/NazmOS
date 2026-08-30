"""Curated goal → domain / finding-category / agent mapping (Phase 7, §10).

Replaces the Phase-4/5 metric-name heuristics (`GOAL_ACTION_ALIGNMENT` keyed on raw
metric strings) with a deterministic, curated mapping. Each goal type maps to one or
more audit domains, finding categories, and responsible agents. Multiple domains per
goal are supported.

This is the single source of truth for "what is NazmOS doing about my goal?"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GoalType:
    key: str
    label: str
    metric: str           # the measurable metric (business_goals.metric)
    direction: str        # decrease | increase | maintain
    domains: list[str]    # audit domains
    categories: list[str] # finding categories
    agents: list[str]     # responsible agents


GOAL_TYPES: list[GoalType] = [
    GoalType("reduce_dead_stock", "Reduce dead inventory", "dead_stock_value", "decrease",
             ["inventory", "recovery_match"], ["dead_stock"], ["recovery", "inventory"]),
    GoalType("improve_margin", "Improve gross margin", "gross_margin", "increase",
             ["money_audit", "inventory"], ["margin_leakage", "thin_margin"], ["margin", "procurement"]),
    GoalType("reduce_stockouts", "Reduce stockouts", "stockout_risk", "decrease",
             ["inventory", "money_audit"], ["stockout_risk"], ["inventory", "procurement"]),
    GoalType("reduce_purchase_cost", "Reduce purchasing cost", "supplier_cost", "decrease",
             ["inventory"], ["supplier_cost", "supplier_price"], ["procurement", "margin"]),
    GoalType("increase_revenue", "Increase revenue", "revenue", "increase",
             ["money_audit"], ["revenue"], ["recovery", "margin"]),
]

GOAL_TYPE_BY_KEY: dict[str, GoalType] = {g.key: g for g in GOAL_TYPES}


def domains_for_goal(goal_type_key: str) -> list[str]:
    g = GOAL_TYPE_BY_KEY.get(goal_type_key)
    return g.domains if g else []


def categories_for_goal(goal_type_key: str) -> list[str]:
    g = GOAL_TYPE_BY_KEY.get(goal_type_key)
    return g.categories if g else []


def agents_for_goal(goal_type_key: str) -> list[str]:
    g = GOAL_TYPE_BY_KEY.get(goal_type_key)
    return g.agents if g else []


def action_alignment(action_type: str) -> list[str]:
    """Goal-type keys this action_type directly serves (deterministic, curated)."""
    mapping = {
        "discount": ["reduce_dead_stock"],
        "transfer_inventory": ["reduce_dead_stock", "reduce_stockouts"],
        "recovery_match": ["reduce_dead_stock"],
        "margin_fix": ["improve_margin", "reduce_purchase_cost"],
        "pricing_increase": ["improve_margin"],
        "pricing_decrease": ["reduce_dead_stock"],
        "restock": ["reduce_stockouts"],
    }
    return mapping.get(action_type, [])


def list_goal_types() -> list[dict[str, Any]]:
    """Goal-type catalogue for the goal-definition UX (§11)."""
    return [
        {
            "key": g.key,
            "label": g.label,
            "metric": g.metric,
            "direction": g.direction,
            "domains": g.domains,
            "categories": g.categories,
            "agents": g.agents,
            "measurable": g.metric in ("dead_stock_value", "gross_margin", "stockout_risk", "supplier_cost", "revenue"),
        }
        for g in GOAL_TYPES
    ]
