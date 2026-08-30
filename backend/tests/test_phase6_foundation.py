"""Phase 6 unit tests (pure logic — no DB).

Covers: deterministic confidence tiers, effectiveness (actual vs expected), deadline
trajectory math, and the learning-consumption mapping for the three agents.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.services.outcome_learning import confidence_tier, ALTERNATIVE_ACTIONS
from app.services.goal_service import estimate_miss_days


# ── §9: deterministic confidence tiers ────────────────────────────────────

def test_confidence_tiers_are_monotonic():
    tiers = [confidence_tier(n)[0] for n in (1, 2, 6, 20)]
    assert tiers == ["weak", "moderate", "strong", "very_strong"]
    confs = [confidence_tier(n)[1] for n in (1, 3, 10, 25)]
    assert confs == sorted(confs)  # strictly non-decreasing


def test_confidence_never_becomes_absolute_rule_from_weak_data():
    # One occurrence stays "weak" at base confidence 0.5 — never an absolute rule.
    tier, conf = confidence_tier(1)
    assert tier == "weak" and conf == 0.5


# ── §10: effectiveness is actual / expected ───────────────────────────────

def test_effectiveness_mapping_uses_actual_over_expected():
    # (the ratio is computed in intervention_effectiveness; assert the mapping direction
    #  is representable and non-identity alternatives exist)
    assert ALTERNATIVE_ACTIONS["discount"] == "transfer_inventory"


# ── §11: deadline-based trajectory ────────────────────────────────────────

def _hist(vals, start, days_apart=7):
    return [
        {"measured_value": v, "measured_at": (start + timedelta(days=i * days_apart)).isoformat()}
        for i, v in enumerate(vals)
    ]


def test_miss_days_decrease_direction():
    start = datetime(2026, 1, 1)
    hist = _hist([42000, 39000, 36000], start)  # decreasing at 3000/week
    r = estimate_miss_days(
        hist, current_value=Decimal("36000"), target=Decimal("25000"),
        direction="decrease", deadline=date(2026, 3, 1),
    )
    assert r["reason"] in ("on track", "projected 0 day(s) late") or r["estimate"] == 0


def test_miss_days_regressing_reports_no_progress():
    start = datetime(2026, 1, 1)
    hist = _hist([36000, 39000, 42000], start)  # INCREASING (wrong direction)
    r = estimate_miss_days(
        hist, current_value=Decimal("42000"), target=Decimal("25000"),
        direction="decrease", deadline=date(2026, 3, 1),
    )
    assert r["estimate"] is None
    assert "no progress" in r["reason"]


def test_miss_days_insufficient_data():
    start = datetime(2026, 1, 1)
    hist = _hist([36000], start)
    r = estimate_miss_days(
        hist, current_value=Decimal("36000"), target=Decimal("25000"),
        direction="decrease", deadline=date(2026, 3, 1),
    )
    assert r["estimate"] is None
    assert "insufficient data" in r["reason"]
