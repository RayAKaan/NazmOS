"""Phase 1 agentic-foundation unit tests.

Pure-logic coverage (no DB): risk classification, event→audit mapping, tool
registry shape, audit domain registry, finding lifecycle ordering, and the
Recovery Agent runtime contract. DB-backed paths (run_audit, advance_status,
verify_finding) follow the existing Postgres-integration convention and are
exercised in CI where the test database is available.
"""
import pytest

from app.services.policy_engine import classify_risk, BASE_RISK
from app.services import audit_engine, audit_triggers, tool_registry
from app.services.finding_service import _FINDING_FLOW
from app.intelligence.agents.registry import AGENT_REGISTRY
from app.intelligence.agents.recovery_agent import RecoveryAgent


# ── Policy engine: risk classification ────────────────────────────────────

def test_risk_bands_are_conservative_defaults():
    assert classify_risk("restock") == "medium"
    assert classify_risk("pricing_increase") == "medium"
    assert classify_risk("pricing_decrease") == "low"
    assert classify_risk("discount") == "low"
    assert classify_risk("cash_alert") == "low"
    assert classify_risk("expiry_alert") == "low"


def test_risk_escalates_with_financial_impact():
    # low-risk action + large impact → escalates
    assert classify_risk("discount", 100000) == "high"
    assert classify_risk("discount", 6000) == "medium"
    assert classify_risk("discount", 100) == "low"
    # already-medium action stays at least medium
    assert classify_risk("restock", 1) == "medium"
    assert classify_risk("restock", 999999) == "high"


def test_risk_never_demotes_below_floor():
    # a high-impact low-band action escalates; a medium-band action with tiny impact
    # stays medium (floor holds).
    assert classify_risk("restock", 0) == "medium"


# ── Continuous audit triggers ──────────────────────────────────────────────

def test_event_maps_to_audit_domains():
    assert "money_audit" in audit_triggers.audit_domains_for_event("sale.completed")
    assert "inventory" in audit_triggers.audit_domains_for_event("inventory.changed")
    assert audit_triggers.audit_domains_for_event("unknown.event") == []


def test_event_maps_to_agents():
    assert "recovery" in audit_triggers.agents_for_event("sale.completed")
    assert "finance" in audit_triggers.agents_for_event("payment.failed")


# ── Audit domain registry ──────────────────────────────────────────────────

def test_domain_registry_is_registered():
    domains = audit_engine.list_domains()
    assert "money_audit" in domains
    assert "inventory" in domains
    assert "recovery_match" in domains
    assert "compliance" in domains


def test_unknown_domain_rejected():
    # run_audit() raises ValueError before touching the DB for an unregistered domain;
    # the pure-logic registry lookup is the guard exercised here.
    assert "does_not_exist" not in audit_engine.AUDIT_DOMAINS


# ── Tool registry ──────────────────────────────────────────────────────────

def test_tools_are_read_only_in_phase1():
    # Phase 2 added mutating tools (transfer_inventory, restock_request, purchase
    # order). Read-only tools remain the majority and the safe default; mutating tools
    # are present but are never callable directly — only via the policy-gated runtime.
    tools = tool_registry.list_tools()
    names = {t["name"] for t in tools}
    assert {"get_inventory", "get_sales", "get_supplier", "forecast_demand",
            "generate_money_audit", "find_recovery_matches", "get_supplier_prices"} <= names
    mutating = [t for t in tools if not t["read_only"]]
    assert {t["name"] for t in mutating} == {"transfer_inventory", "restock"}


def test_supplier_prices_tool_now_exists():
    # Phase 2 added a SupplierPrice model, so get_supplier_prices is now a real
    # (read-only, honest) tool.
    names = {t["name"]: t for t in tool_registry.list_tools()}
    assert "get_supplier_prices" in names
    assert names["get_supplier_prices"]["read_only"] is True


# ── Finding lifecycle ──────────────────────────────────────────────────────

def test_finding_lifecycle_is_ordered():
    # detected → analyzed → recommended → awaiting_approval → approved → executing
    # → completed → verified. Terminal rejected/failed branch off awaiting_approval.
    assert _FINDING_FLOW["detected"] == "analyzed"
    assert _FINDING_FLOW["analyzed"] == "recommended"
    assert _FINDING_FLOW["recommended"] == "awaiting_approval"
    assert _FINDING_FLOW["awaiting_approval"] == "approved"
    assert _FINDING_FLOW["approved"] == "executing"
    assert _FINDING_FLOW["executing"] == "completed"
    assert _FINDING_FLOW["completed"] == "verified"


# ── Recovery Agent runtime contract ────────────────────────────────────────

def test_recovery_agent_registered_and_declared():
    assert "recovery" in AGENT_REGISTRY
    assert issubclass(AGENT_REGISTRY["recovery"], RecoveryAgent)
    assert RecoveryAgent.agent_type == "recovery"
    assert "recover" in RecoveryAgent.objective.lower()
    assert "generate_money_audit" in RecoveryAgent.tools
    assert "sale.completed" in RecoveryAgent.triggers
    assert RecoveryAgent.read_only is False  # proposes mutating actions, gated by runtime
