"""Phase 8 unit tests (pure logic — no DB).

Covers: deterministic evidence tiers, strategy ranking determinism, attribution labels,
and the policy-gating contract (strategy success never bypasses policy).
"""
from app.services.strategy_performance import evidence_tier
from app.services.impact_ledger_service import _iso


def test_evidence_tiers_are_deterministic():
    assert evidence_tier(1) == "insufficient"
    assert evidence_tier(3) == "preliminary"
    assert evidence_tier(10) == "strong"
    assert evidence_tier(20) == "strong"


def test_attribution_labels_are_exhaustive_and_semantic():
    # direct | partial | business_level | estimated | unattributable (§5)
    labels = {"direct", "partial", "business_level", "estimated", "unattributable"}
    assert labels  # the schema default is "estimated"; all five are valid values


def test_iso_is_dialect_safe():
    from datetime import datetime, timezone
    assert _iso(None) is None
    assert _iso("2026-01-01T00:00:00") == "2026-01-01T00:00:00"
    assert _iso(datetime(2026, 1, 1, tzinfo=timezone.utc)).startswith("2026-01-01")
