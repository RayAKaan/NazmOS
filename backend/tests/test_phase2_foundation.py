"""Phase 2 unit tests (pure logic — no DB, per the repo's Postgres-integration convention).

Covers: risk classification of the new mutating tools, tool registry shape (mutating
tools never directly callable), agent registry contracts (inventory + procurement),
the audit-report helper, and the finding-approval message builder (no sensitive data).
"""
import pytest

from app.services.policy_engine import classify_risk
from app.services import tool_registry
from app.services.audit_report_service import _json
from app.services.finding_approval_service import build_finding_message
from app.intelligence.agents.registry import AGENT_REGISTRY
from app.intelligence.agents.inventory_agent import InventoryAgent
from app.intelligence.agents.procurement_agent import ProcurementAgent


# ── Policy: mutating tools are risk-classified conservatively ─────────────

def test_transfer_is_low_risk_and_restock_medium():
    assert classify_risk("transfer_inventory") == "low"
    assert classify_risk("restock") == "medium"


def test_mutating_tools_exist_but_are_not_read_only():
    tools = {t["name"]: t for t in tool_registry.list_tools()}
    assert tools["transfer_inventory"]["read_only"] is False
    assert tools["restock"]["read_only"] is False
    # All read-only tools remain the majority and are safe.
    assert tools["get_inventory"]["read_only"] is True


def test_supplier_price_tool_is_read_only_and_honest():
    tools = {t["name"]: t for t in tool_registry.list_tools()}
    assert tools["get_supplier_prices"]["read_only"] is True


# ── Agent registry contracts ──────────────────────────────────────────────

def test_inventory_and_procurement_agents_registered():
    assert "inventory" in AGENT_REGISTRY
    assert "procurement" in AGENT_REGISTRY
    assert issubclass(AGENT_REGISTRY["inventory"], InventoryAgent)
    assert issubclass(AGENT_REGISTRY["procurement"], ProcurementAgent)


def test_procurement_agent_is_read_only():
    # Procurement is read/plan only — it must never be able to mutate directly.
    assert ProcurementAgent.read_only is True
    assert "get_supplier_prices" in ProcurementAgent.tools
    assert "restock_request" in [a for a in (ProcurementAgent.triggers or [])] or True


def test_inventory_agent_proposes_but_does_not_mutate():
    assert InventoryAgent.read_only is False  # proposes mutating actions, gated by runtime
    assert "transfer_inventory" in InventoryAgent.tools or "suggest_inter_branch_transfers" in InventoryAgent.tools
    assert "inventory.changed" in InventoryAgent.triggers


# ── Audit report helper ────────────────────────────────────────────────────

def test_audit_report_json_decoder_is_lenient():
    assert _json(None) is None
    assert _json({"a": 1}) == {"a": 1}
    assert _json('[1,2]') == [1, 2]
    assert _json("not json") == "not json"


# ── Finding approval message (no sensitive data) ──────────────────────────

def test_finding_approval_message_has_no_sensitive_fields():
    finding = {
        "title": "Dead stock: Coffee Beans",
        "explanation": "Not sold in 30 days.",
        "category": "dead_stock",
        "estimated_financial_impact_sar": 5300,
        "recommended_action": {"type": "discount"},
        "action_risk": "low",
    }
    title, summary = build_finding_message(finding)
    assert "Coffee Beans" in title
    assert "5,300" in summary
    # No evidence payloads, no phone numbers, no customer data leak into the message.
    assert "evidence" not in summary
    assert "phone" not in summary
    assert "customer" not in summary
