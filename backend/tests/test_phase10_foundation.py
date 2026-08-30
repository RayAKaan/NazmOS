"""Phase 10 unit tests (pure logic — no DB).

Covers: deterministic recency weighting (never erases history), recommendation stability
(hysteresis), and root-cause confidence labels.
"""
from datetime import datetime, timedelta, timezone

from app.services.strategy_performance import recency_weight, RECENCY_HALF_LIFE_DAYS
from app.services.decision_scoring import apply_stability, MIN_SCORE_DELTA
from app.services.root_cause import CONFIDENCE_LABELS


# ── §11–13: recency weighting ─────────────────────────────────────────────

def test_recency_weight_is_monotonic_and_bounded():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent = recency_weight(now - timedelta(days=1), now)
    old = recency_weight(now - timedelta(days=365), now)
    assert 0 < old < recent <= 1.0


def test_recency_half_life_is_exact():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    at_half_life = recency_weight(now - timedelta(days=RECENCY_HALF_LIFE_DAYS), now)
    assert abs(at_half_life - 0.5) < 1e-6


def test_recency_never_negative_or_over_one():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert recency_weight(now + timedelta(days=100), now) == 1.0  # future/zero-age clamped
    assert recency_weight(None, now) == 1.0


# ── §23: recommendation stability ─────────────────────────────────────────

def test_stability_keeps_previous_when_scores_tied():
    ranked = [
        {"action_type": "discount", "score": 0.50},
        {"action_type": "transfer_inventory", "score": 0.49},
    ]
    # within MIN_SCORE_DELTA → previous (transfer) kept first
    out = apply_stability(ranked, previous_selection="transfer_inventory")
    assert out[0]["action_type"] == "transfer_inventory"


def test_stability_flips_on_meaningful_difference():
    ranked = [
        {"action_type": "discount", "score": 0.80},
        {"action_type": "transfer_inventory", "score": 0.49},
    ]
    # > MIN_SCORE_DELTA → meaningful change wins regardless of previous selection
    out = apply_stability(ranked, previous_selection="transfer_inventory")
    assert out[0]["action_type"] == "discount"


def test_stability_no_previous_selection_is_noop():
    ranked = [{"action_type": "discount", "score": 0.5}, {"action_type": "transfer_inventory", "score": 0.49}]
    assert apply_stability(ranked, None) == ranked


# ── §18: root-cause confidence labels ─────────────────────────────────────

def test_root_cause_confidence_labels():
    assert set(CONFIDENCE_LABELS) == {"supported", "plausible", "insufficient_evidence"}
