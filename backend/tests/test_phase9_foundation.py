"""Phase 9 unit tests (pure logic — no DB).

Covers: deterministic decision scoring + normalization, urgency model, and the
documented boundary that scoring ≠ policy (§13).
"""
from app.services.decision_scoring import (
    compute_recommendation_score, normalize_impact_sar, normalize_urgency,
    normalize_data_quality, normalize_strategy, WEIGHTS,
)
from app.services.audit_engine import compute_urgency
from app.services.strategy_performance import ATTRIBUTION_WEIGHT


def test_normalization_scales_and_clamps():
    # log-scale impact maps small→small, large→near-1
    assert normalize_impact_sar(0) == 0.0
    assert normalize_impact_sar(100) < normalize_impact_sar(100_000)
    assert 0 <= normalize_impact_sar(10_000_000) <= 1.0  # clamped at cap


def test_data_quality_normalization():
    assert normalize_data_quality(94) == 0.94
    assert normalize_data_quality(None) == 0.5  # neutral default
    assert normalize_data_quality(150) == 1.0  # clamped


def test_urgency_is_deterministic():
    assert compute_urgency("critical", 0) == "critical"
    assert compute_urgency("medium", 25000) == "high"      # large exposure escalates medium
    assert compute_urgency("low", 100000) == "low"          # value alone never escalates low
    assert compute_urgency("high", 100, recurring=True) == "critical"  # recurrence escalates


def test_urgency_normalization_map():
    assert normalize_urgency("critical") == 1.0
    assert normalize_urgency("low") == 0.25


def test_strategy_normalization_insufficient_evidence_is_zero():
    # §18: insufficient evidence never masquerades as strong strategy knowledge.
    assert normalize_strategy({"effectiveness": 0.95, "success_rate": 0.95, "evidence_tier": "insufficient"}) == 0.0
    strong = normalize_strategy({"effectiveness": 0.8, "success_rate": 0.8, "evidence_tier": "strong"})
    assert strong > 0.0


def test_score_is_bounded_and_risk_subtracts():
    hi = compute_recommendation_score(
        goal_alignment="directly_aligned", estimated_impact_sar=50000, urgency="critical",
        confidence=0.95, data_quality_score=100,
        strategy={"effectiveness": 0.9, "success_rate": 0.9, "attempts": 20, "evidence_tier": "strong"},
        risk="low",
    )
    lo = compute_recommendation_score(
        goal_alignment="unrelated", estimated_impact_sar=100, urgency="low",
        confidence=0.5, data_quality_score=50,
        strategy={"effectiveness": 0.0, "success_rate": None, "attempts": 0, "evidence_tier": "insufficient"},
        risk="high",
    )
    assert 0 <= lo["score"] < hi["score"] <= 1.0


def test_weights_are_documented_and_bounded():
    # Non-risk weights sum to 0.90; risk subtracts 0.10 → max possible = 1.0.
    assert round(sum(v for k, v in WEIGHTS.items() if k != "risk"), 2) == 0.90
    assert WEIGHTS["risk"] == 0.10


def test_attribution_weights_are_ordered():
    # §7: direct > partial > business_level > estimated/unattributable.
    assert ATTRIBUTION_WEIGHT["direct"] > ATTRIBUTION_WEIGHT["partial"] > ATTRIBUTION_WEIGHT["business_level"]
    assert ATTRIBUTION_WEIGHT["estimated"] == 0.0
    assert ATTRIBUTION_WEIGHT["unattributable"] == 0.0
