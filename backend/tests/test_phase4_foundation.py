"""Phase 4 unit tests (pure logic — no DB, per repo convention).

Covers: deterministic goal progress, goal→action alignment, outcome-learning memory
kinds, configurable thresholds (safety floors), recurring-problem params, graph
projector registration, and orchestrator goal-awareness.
"""
from decimal import Decimal

import pytest

from app.services.goal_service import compute_progress
from app.services.orchestrator import GOAL_ACTION_ALIGNMENT, _aligns_with_goal
from app.services.policy_engine import BASE_RISK, IMPACT_ESCALATE_MEDIUM, IMPACT_ESCALATE_HIGH
from app.services.recurring_detection import RECURRENCE_WINDOW_DAYS, RECURRENCE_THRESHOLD
from app.services.knowledge_graph import _GRAPH_PROJECTOR_MAP
from app.database.models import MemoryKind


# ── Goals: deterministic progress (§2–3) ──────────────────────────────────

def test_progress_decrease():
    p = compute_progress(Decimal("42000"), Decimal("31500"), Decimal("25000"), "decrease")
    assert p["trajectory"] == "on_track"
    assert 0 < p["progress_pct"] <= 100


def test_progress_decrease_achieved():
    p = compute_progress(Decimal("42000"), Decimal("20000"), Decimal("25000"), "decrease")
    assert p["trajectory"] == "achieved"
    assert p["remaining_gap"] <= 0


def test_progress_increase():
    p = compute_progress(Decimal("18"), Decimal("20"), Decimal("22"), "increase")
    assert p["progress_pct"] == pytest.approx(50.0, abs=0.2)


def test_progress_unknown_without_baseline():
    p = compute_progress(None, Decimal("31500"), Decimal("25000"), "decrease")
    assert p["progress_pct"] is None
    assert p["trajectory"] == "unknown"


# ── Goal-aware orchestration (§4) ─────────────────────────────────────────

def test_goal_action_alignment_mapping():
    assert "discount" in GOAL_ACTION_ALIGNMENT["dead_stock_value"]
    assert "margin_fix" in GOAL_ACTION_ALIGNMENT["gross_margin"]
    assert "restock" in GOAL_ACTION_ALIGNMENT["stockout_risk"]


def test_aligns_with_goal_deterministic():
    # Phase 7 §12: alignment is now a three-way string (directly_aligned / unrelated),
    # using the curated goal→action mapping for known goal types.
    goals = [{"metric": "dead_stock_value", "status": "active"}]
    assert _aligns_with_goal(goals, "discount") == "directly_aligned"
    assert _aligns_with_goal(goals, "restock") == "unrelated"
    assert _aligns_with_goal([], "discount") == "unrelated"


# ── Policy: configurable thresholds with safety floors (§13) ──────────────

def test_risk_thresholds_never_below_default_floor():
    # The defaults are 5000/20000; config can only raise them, never lower.
    assert IMPACT_ESCALATE_MEDIUM >= Decimal("5000")
    assert IMPACT_ESCALATE_HIGH >= Decimal("20000")


def test_base_risk_bands_include_new_action_types():
    assert BASE_RISK["transfer_inventory"] == "low"
    assert BASE_RISK["margin_fix"] == "medium"
    assert BASE_RISK["restock"] == "medium"


# ── Outcome learning memory kinds (§8) ────────────────────────────────────

def test_memory_kinds_are_distinct():
    kinds = {k.value for k in MemoryKind}
    assert kinds == {"fact", "inference", "preference", "hypothesis"}


# ── Recurring problems (§23) ──────────────────────────────────────────────

def test_recurrence_params_are_conservative():
    assert RECURRENCE_THRESHOLD >= 3
    assert RECURRENCE_WINDOW_DAYS >= 30


# ── Knowledge graph (§9) ──────────────────────────────────────────────────

def test_new_phase4_projectors_registered():
    for evt in ("action.completed", "supplier_price.changed", "finding.created"):
        assert evt in _GRAPH_PROJECTOR_MAP, f"{evt} projector missing"
