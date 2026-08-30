"""Phase 11 unit tests (pure logic — no DB).

Covers: regime detection, freshness states, recommendation-stability safety override, and
the root-cause→recommendation quality gates.
"""
from app.services.regime_detection import detect_regime, regime_relevance_multiplier
from app.services.operational_health import freshness_state
from app.services.decision_scoring import apply_stability
from app.services.root_cause import ROOT_CAUSE_STRATEGIES


# ── §Part 9: regime detection ─────────────────────────────────────────────

def test_regime_no_signal_when_stable():
    r = detect_regime([100, 98, 102, 99, 101, 100], [101, 100, 99])
    assert r["state"] == "no_signal"


def test_regime_supported_change_on_large_shift():
    r = detect_regime([100, 98, 102, 99, 101, 100], [20, 22, 18])
    assert r["state"] == "supported_change"


def test_regime_insufficient_data():
    r = detect_regime([100, 99], [20])
    assert r["state"] == "insufficient_data"


def test_regime_relevance_multiplier_bounded():
    assert regime_relevance_multiplier("no_signal") == 1.0
    assert regime_relevance_multiplier("supported_change") == 0.4
    assert 0 < regime_relevance_multiplier("possible_change") < 1.0


# ── §Part 7: freshness states ─────────────────────────────────────────────

def test_freshness_four_states():
    assert freshness_state(1, 10) == "fresh"
    assert freshness_state(15, 10) == "aging"
    assert freshness_state(25, 10) == "stale"
    assert freshness_state(None, 10) == "unknown"


# ── §Part 11: stability must never override safety ────────────────────────

def test_stability_does_not_retain_unsafe_strategy():
    ranked = [
        {"action_type": "discount", "score": 0.50, "risk": "low"},
        {"action_type": "transfer_inventory", "score": 0.49, "risk": "high"},
    ]
    # previous = transfer, but transfer is now high-risk → must NOT be retained.
    out = apply_stability(ranked, previous_selection="transfer_inventory")
    assert out[0]["action_type"] == "discount"


def test_stability_retains_safe_previous_on_tie():
    ranked = [
        {"action_type": "discount", "score": 0.50, "risk": "low"},
        {"action_type": "transfer_inventory", "score": 0.49, "risk": "low"},
    ]
    out = apply_stability(ranked, previous_selection="transfer_inventory")
    assert out[0]["action_type"] == "transfer_inventory"


# ── §Part 3–5: root-cause → recommendation mapping ────────────────────────

def test_root_cause_strategy_mapping_exists():
    assert "margin_fix" in ROOT_CAUSE_STRATEGIES["supplier_cost_increase"]["strategies"]
    assert ROOT_CAUSE_STRATEGIES["missing_cost_data"]["strategies"] == []  # no action, gather data
    assert "discount" in ROOT_CAUSE_STRATEGIES["low_demand"]["strategies"]
