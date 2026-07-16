"""Unit tests for recovery match safety and scoring logic.

These tests exercise the pure functions and business rules in the recovery
match module WITHOUT requiring a database.  They cover the highest-risk
surface: category gating, expiry safety, distance calculation, match scoring,
and the minimum-score / days-left thresholds.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.services.recovery_match_service import (
    DEFAULT_MAX_DISTANCE_KM,
    _compute_match_score,
    _distance_km,
    _expiry_is_safe,
    _is_category_allowed,
)


# ---------------------------------------------------------------------------
# _is_category_allowed
# ---------------------------------------------------------------------------
class TestIsCategoryAllowed:
    def test_medicine_keyword_rejects(self):
        assert _is_category_allowed("medicine", None) is False

    def test_arabic_pharma_keyword_rejects(self):
        assert _is_category_allowed("دواء", None) is False

    def test_baby_in_item_name_rejects(self):
        assert _is_category_allowed(None, "baby formula 400g") is False

    def test_frozen_storage_type_rejects(self):
        assert _is_category_allowed("Dairy Products", "Milk", "frozen") is False

    def test_allowed_beverages_category(self):
        assert _is_category_allowed("beverages", "Coffee Beans 250g", None) is True

    def test_all_none_inputs(self):
        assert _is_category_allowed(None, None, None) is True

    def test_case_insensitive_rejection(self):
        assert _is_category_allowed("Medicine", None) is False

    def test_cosmetic_rejects(self):
        assert _is_category_allowed("cosmetic", "Face Cream") is False

    def test_arabic_dairy_keyword_rejects(self):
        assert _is_category_allowed("ألبان", "حليب طازج") is False

    def test_dates_category_allowed(self):
        assert _is_category_allowed("dates", "Sukkari 1kg", None) is True

    def test_meat_keyword_rejects(self):
        assert _is_category_allowed("meat", "Chicken Breast") is False

    def test_arabic_frozen_keyword_rejects(self):
        assert _is_category_allowed("مجمد", "Pizza") is False


# ---------------------------------------------------------------------------
# _expiry_is_safe
# ---------------------------------------------------------------------------
class TestExpiryIsSafe:
    def test_none_expiry_rejects(self):
        ok, reason = _expiry_is_safe(None, "General")
        assert ok is False
        assert reason == "expiry_date_required_for_real_match"

    def test_food_category_89_days_rejects(self):
        ok, reason = _expiry_is_safe(date.today() + timedelta(days=89), "food")
        assert ok is False
        assert "expiry_too_close" in reason

    def test_food_category_90_days_passes(self):
        ok, reason = _expiry_is_safe(date.today() + timedelta(days=90), "food")
        assert ok is True
        assert reason is None

    def test_general_category_59_days_rejects(self):
        ok, reason = _expiry_is_safe(date.today() + timedelta(days=59), "cleaning")
        assert ok is False
        assert "expiry_too_close" in reason

    def test_general_category_60_days_passes(self):
        ok, reason = _expiry_is_safe(date.today() + timedelta(days=60), "cleaning")
        assert ok is True
        assert reason is None

    def test_arabic_food_keyword_triggers_90_day_threshold(self):
        ok, reason = _expiry_is_safe(date.today() + timedelta(days=89), "قهوة")
        assert ok is False
        assert "min_90" in reason

    def test_expired_date_rejects(self):
        ok, reason = _expiry_is_safe(date.today() - timedelta(days=5), "snack")
        assert ok is False

    def test_beverage_triggers_food_threshold(self):
        ok, reason = _expiry_is_safe(date.today() + timedelta(days=89), "beverage")
        assert ok is False

    def test_dates_category_triggers_food_threshold(self):
        ok, reason = _expiry_is_safe(date.today() + timedelta(days=89), "dates")
        assert ok is False

    def test_storage_type_food_triggers_food_threshold(self):
        ok, reason = _expiry_is_safe(date.today() + timedelta(days=89), None, "snack")
        assert ok is False


# ---------------------------------------------------------------------------
# _distance_km
# ---------------------------------------------------------------------------
class TestDistanceKm:
    def test_same_point_zero(self):
        assert _distance_km(24.7136, 46.6753, 24.7136, 46.6753) == 0.0

    def test_riyadh_to_jeddah_approximate(self):
        # Riyadh ~24.7136°N, 46.6753°E → Jeddah ~21.4858°N, 39.1925°E
        d = _distance_km(24.7136, 46.6753, 21.4858, 39.1925)
        assert d is not None
        assert 800 < d < 1000  # ~845 km

    def test_none_lat_returns_none(self):
        assert _distance_km(None, 46.6753, 21.4858, 39.1925) is None

    def test_none_lon_returns_none(self):
        assert _distance_km(24.7136, None, 21.4858, 39.1925) is None

    def test_invalid_string_coords_returns_none(self):
        assert _distance_km("not_a_number", "bad", 21.0, 39.0) is None

    def test_opposite_points_near_half_earth(self):
        # 0°N, 0°E → 0°N, 180°E
        d = _distance_km(0, 0, 0, 180)
        assert d is not None
        assert 20000 < d < 20100

    def test_small_distance_accurate(self):
        # Two points ~1 km apart
        d = _distance_km(24.7136, 46.6753, 24.7226, 46.6753)
        assert d is not None
        assert 0.9 < d < 1.1


# ---------------------------------------------------------------------------
# _compute_match_score
# ---------------------------------------------------------------------------
class TestComputeMatchScore:
    def test_base_score_name_only(self):
        # No barcode, no SKU, high days_left → 40 + 0 = 40
        assert _compute_match_score(None, None, days_left=10, distance=10) == 40

    def test_barcode_match(self):
        # 40 + 40 = 80 (high days_left → no urgency bonus)
        assert _compute_match_score("628000000001", None, days_left=10, distance=10) == 80

    def test_sku_match(self):
        # 40 + 25 = 65 (high days_left → no urgency bonus)
        assert _compute_match_score(None, "SKU-001", days_left=10, distance=10) == 65

    def test_urgency_bonus(self):
        # 1 day left → urgency = max(0, 20 - 2) = 18; barcode(80) → 98
        assert _compute_match_score("628000000001", None, days_left=1, distance=10) == 98

    def test_proximity_bonus(self):
        # barcode(80) + proximity(5) = 85 (high days_left → no urgency bonus)
        assert _compute_match_score("628000000001", None, days_left=10, distance=2) == 85

    def test_score_capped_at_100(self):
        # barcode(80) + urgency(20) + proximity(5) = 105 → capped at 100
        assert _compute_match_score("628000000001", None, days_left=0.5, distance=1) == 100

    def test_score_exactly_75_passes(self):
        # SKU(65) + urgency(10, 5 days) = 75
        assert _compute_match_score(None, "SKU-001", days_left=5, distance=10) == 75

    def test_score_74_rejected(self):
        # SKU(65) + urgency(8, 6 days) = 73
        score = _compute_match_score(None, "SKU-001", days_left=6, distance=10)
        assert score < 75

    def test_name_only_never_passes(self):
        # Base 40 + max urgency 20 = 60 < 75
        assert _compute_match_score(None, None, days_left=0, distance=10) == 60

    def test_far_distance_no_proximity_bonus(self):
        # barcode(80) + no proximity = 80
        assert _compute_match_score("628000000001", None, days_left=10, distance=10) == 80

    def test_zero_distance_gets_proximity_bonus(self):
        # barcode(80) + proximity(5) = 85
        assert _compute_match_score("628000000001", None, days_left=10, distance=0) == 85

    def test_none_distance_no_proximity_bonus(self):
        # barcode(80) + no proximity = 80
        assert _compute_match_score("628000000001", None, days_left=10, distance=None) == 80


# ---------------------------------------------------------------------------
# Threshold constants sanity
# ---------------------------------------------------------------------------
class TestConstants:
    def test_default_max_distance_is_5km(self):
        assert DEFAULT_MAX_DISTANCE_KM == 5.0

    def test_excluded_keywords_include_medicine(self):
        from app.services.recovery_match_service import EXCLUDED_CATEGORY_KEYWORDS
        assert "medicine" in EXCLUDED_CATEGORY_KEYWORDS

    def test_excluded_keywords_include_arabic_terms(self):
        from app.services.recovery_match_service import EXCLUDED_CATEGORY_KEYWORDS
        assert "دواء" in EXCLUDED_CATEGORY_KEYWORDS
        assert "مجمد" in EXCLUDED_CATEGORY_KEYWORDS

    def test_min_food_shelf_life_is_90(self):
        from app.services.recovery_match_service import MIN_FOOD_SHELF_LIFE_DAYS
        assert MIN_FOOD_SHELF_LIFE_DAYS == 90

    def test_min_general_shelf_life_is_60(self):
        from app.services.recovery_match_service import MIN_GENERAL_SHELF_LIFE_DAYS
        assert MIN_GENERAL_SHELF_LIFE_DAYS == 60
