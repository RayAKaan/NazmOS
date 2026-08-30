"""Phase 7 unit tests (pure logic — no DB).

Covers: curated goal→domain mapping, goal→action alignment, and the recovery agent's
Finding-driven contract.
"""
from app.services.goal_domains import (
    list_goal_types, domains_for_goal, categories_for_goal, agents_for_goal, action_alignment,
)
from app.services.orchestrator import _aligns_with_goal
from app.intelligence.agents.recovery_agent import RecoveryAgent


def test_goal_type_catalogue_is_curated():
    types = list_goal_types()
    keys = {t["key"] for t in types}
    assert {"reduce_dead_stock", "improve_margin", "reduce_stockouts", "reduce_purchase_cost", "increase_revenue"} <= keys


def test_goal_domain_mapping_is_multi_domain():
    # Reduce dead stock → inventory + recovery_match (multiple domains per goal, §10).
    assert set(domains_for_goal("reduce_dead_stock")) == {"inventory", "recovery_match"}
    assert set(agents_for_goal("improve_margin")) == {"margin", "procurement"}
    assert "dead_stock" in categories_for_goal("reduce_dead_stock")


def test_action_alignment_is_deterministic():
    assert "reduce_dead_stock" in action_alignment("discount")
    assert "reduce_stockouts" in action_alignment("restock")
    assert "improve_margin" in action_alignment("margin_fix")


def test_orchestrator_alignment_uses_curated_mapping():
    # A known goal type (metric = a goal-type key) → curated mapping.
    assert _aligns_with_goal([{"metric": "dead_stock_value", "status": "active"}], "discount") == "directly_aligned"
    assert _aligns_with_goal([{"metric": "dead_stock_value", "status": "active"}], "restock") == "unrelated"
    # No active goals → unrelated.
    assert _aligns_with_goal([], "discount") == "unrelated"


def test_recovery_agent_contract_is_finding_driven():
    # Phase 7 §2: recovery must propose with finding_id so lineage is complete.
    assert RecoveryAgent.agent_type == "recovery"
    assert "recover" in RecoveryAgent.objective.lower()
    # The agent's propose() consumes findings (verified in integration test); the
    # contract here is that it still proposes mutating actions, gated by the runtime.
    assert RecoveryAgent.read_only is False
