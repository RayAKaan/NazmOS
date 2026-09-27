"""Phase 3K — Loop Console (read-only) module tests. DB-free.

Validates the read-only owner console over the loop spine:
    * the policy endpoint surfaces the deterministic contract verbatim;
    * verified-outcome reads fail closed when the ledger is not configured
      (empty path) — never a fabricated number;
    * DLP cleanliness of the policy surface (no business data, DLP-clean).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.business_loop.contracts import (
    CycleStage,
    GovernanceOutcome,
    ImpactKind,
    RecommendationStatus,
    RECOMMENDATION_TRANSITIONS,
    VerificationStatus,
)
from app.services.business_loop.opportunity import DEFAULT_RULE_OVERRIDES, RULE_VERSIONS

ROUTER_PATH = Path(__file__).resolve().parents[1] / "app" / "routers" / "loop_console.py"
ROUTER_SRC = ROUTER_PATH.read_text(encoding="utf-8")


def test_policy_endpoint_is_read_only():
    """The loop console must NEVER contain a write-capable verb (no PUT/POST/PATCH/DELETE)."""
    for verb in ("@router.post", "@router.put", "@router.patch", "@router.delete"):
        assert verb not in ROUTER_SRC, f"loop console became writable: {verb}"

    assert "@router.get" in ROUTER_SRC


def test_loop_console_reuses_existing_ledger_not_a_new_store():
    """3K must READ the existing V1 OutcomeLedger path, not create a parallel store."""
    assert "outcome_ledger" in ROUTER_SRC or "latest_verified_impact" in ROUTER_SRC
    assert "OutputLedger" not in ROUTER_SRC  # no accidental parallel class
    assert "CREATE TABLE" not in ROUTER_SRC


def test_loop_console_is_dlp_clean_source():
    """Console code must never READ raw merchant fields (data-access patterns)."""
    for forbidden in ('"sku"', ".sku", '"stock_count"', '"business_name"', "stock_count"):
        assert forbidden not in ROUTER_SRC, f"loop console touches {forbidden}"


def test_policy_contract_verbatim():
    """Policy endpoint must mirror the deterministic loop contract (no drift)."""
    assert '"rule_versions": RULE_VERSIONS' in ROUTER_SRC
    assert 'DEFAULT_RULE_OVERRIDES' in ROUTER_SRC
    assert 'CycleStage.ordered()' in ROUTER_SRC
    assert 'RECOMMENDATION_TRANSITIONS' in ROUTER_SRC
    assert len(CycleStage.ordered()) == 21
    assert len(VerificationStatus) == 6
    assert len([i for i in ImpactKind]) == 5
    assert len([g for g in GovernanceOutcome]) == 5
    assert len(RecommendationStatus) >= 16


def test_policy_detection_thresholds_are_documented():
    """The deterministic thresholds surfaced must equal opportunity.py's."""
    assert DEFAULT_RULE_OVERRIDES["surplus_min_days_supply"] == 30
    assert DEFAULT_RULE_OVERRIDES["surplus_min_value_sar"] == 500.0
    assert DEFAULT_RULE_OVERRIDES["stockout_max_days_supply"] == 5
    assert DEFAULT_RULE_OVERRIDES["target_margin_pct"] == 0.22


def test_verified_outcome_read_fails_closed_when_unconfigured():
    """Empty ledger path → all-zero report, never a fabricated number."""
    assert "if not path:" in ROUTER_SRC
    assert 'return {"configured": False, "verified_rows": 0' in ROUTER_SRC


def test_transition_contract_complete():
    """The terminal lifecycle statuses must be final (no outgoing transitions)."""
    for terminal in ("closed", "partial", "disputed", "unverified", "denied", "expired", "superseded"):
        status = RecommendationStatus(terminal)
        assert RECOMMENDATION_TRANSITIONS[status] == set(), f"{terminal} must be terminal"