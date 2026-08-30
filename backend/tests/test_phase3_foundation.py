"""Phase 3 unit tests (pure logic — no DB, per the repo convention).

Covers: cost estimation, re-audit domain mapping, scheduled-audit domain list,
orchestrator agent subset, margin agent contract, graph projector registration,
and event-type additions.
"""
import pytest

from app.services.agent_observability import estimate_cost_usd, PROVIDER_RATES
from app.services.reaudit import domains_for_action
from app.services.orchestrator import ORCHESTRATED_AGENTS
from app.services.knowledge_graph import _GRAPH_PROJECTOR_MAP
from app.services.weekly_report_service import DOMAIN_DIMENSION, DIMENSIONS
from app.intelligence.agents.registry import AGENT_REGISTRY
from app.intelligence.agents.margin_agent import MarginAgent


# ── Cost control (§25) ────────────────────────────────────────────────────

def test_cost_estimate_is_zero_for_deterministic_and_mock():
    assert estimate_cost_usd("deterministic", 1000, 500) == 0.0
    assert estimate_cost_usd("mock", 1000, 500) == 0.0


def test_cost_estimate_scales_with_tokens():
    c1 = estimate_cost_usd("groq", 1_000_000, 1_000_000)
    c2 = estimate_cost_usd("groq", 2_000_000, 2_000_000)
    assert c2 > c1 > 0
    assert "groq" in PROVIDER_RATES and "google" in PROVIDER_RATES


# ── Re-audit after action (§3) ────────────────────────────────────────────

def test_action_domain_mapping_is_selective():
    assert domains_for_action("transfer_inventory") == ["inventory", "recovery_match"]
    assert domains_for_action("restock") == ["inventory"]
    assert domains_for_action("pricing_increase") == ["money_audit"]
    # Unknown / trivial action types re-audit nothing (never a full multi-domain audit).
    assert domains_for_action("review") == []
    assert domains_for_action("unknown_action") == []


# ── Scheduled audit domains (§2) ──────────────────────────────────────────

def test_scheduled_audit_domains_are_bounded():
    from app.tasks.audit_tasks import ALL_DOMAINS
    assert set(ALL_DOMAINS) == {"money_audit", "inventory", "recovery_match", "compliance"}


# ── Orchestrator (§11–12) ─────────────────────────────────────────────────

def test_orchestrator_uses_curated_agent_subset():
    # Least privilege: the orchestrator delegates to a curated subset, not every agent,
    # and never includes read-only informational agents in the delegation set.
    assert set(ORCHESTRATED_AGENTS) <= set(AGENT_REGISTRY.keys())
    assert "finance" not in ORCHESTRATED_AGENTS  # finance is read-only, not delegated
    assert "compliance" not in ORCHESTRATED_AGENTS


# ── Margin agent (§10) ────────────────────────────────────────────────────

def test_margin_agent_registered_and_read_plan():
    assert "margin" in AGENT_REGISTRY
    assert issubclass(AGENT_REGISTRY["margin"], MarginAgent)
    assert MarginAgent.read_only is False  # proposes margin_fix, gated by runtime
    assert "get_supplier_prices" in MarginAgent.tools
    assert "price.updated" in MarginAgent.triggers


# ── Knowledge graph (§6–7) ────────────────────────────────────────────────

def test_new_graph_projectors_registered():
    for evt in ("price.updated", "inventory.changed", "transfer.completed", "finding.created"):
        assert evt in _GRAPH_PROJECTOR_MAP, f"{evt} projector missing"


# ── Health score dimensions (§18) ─────────────────────────────────────────

def test_health_dimensions_cover_the_expected_axes():
    assert set(DIMENSIONS) == {"inventory", "margins", "procurement", "cash", "sales", "compliance", "operations"}
    assert DOMAIN_DIMENSION["money_audit"] == "margins"
    assert DOMAIN_DIMENSION["inventory"] == "inventory"
    assert DOMAIN_DIMENSION["compliance"] == "compliance"
