from decimal import Decimal

import pytest

from app.services.recovery_intelligence import classify_inventory, estimate_recovery, stockout_financials


def test_financial_measures_are_separate_and_no_fake_expected_recovery():
    result = estimate_recovery(
        classification="DEAD",
        stock=Decimal("100"),
        cost=Decimal("10"),
        sell=Decimal("15"),
    )
    assert result.inventory_value == Decimal("1000.00")
    assert result.capital_at_risk == Decimal("1000.00")
    assert result.recoverable_low == Decimal("0.00")
    assert result.recoverable_high == Decimal("1000.00")
    assert result.expected_recovery is None


def test_seasonal_or_uncertain_items_are_not_forced_dead():
    assert classify_inventory(
        stock=Decimal("50"), recent_qty_30=Decimal("0"), prior_qty_30=Decimal("80"),
        days_since_last_sale=65, inventory_age_days=70, seasonal_index=Decimal("2.0")
    ) == "SEASONAL"


def test_stockout_is_revenue_and_profit_risk_not_recovered_cash():
    result = stockout_financials(
        stock=Decimal("10"), daily_velocity=Decimal("5"), sell=Decimal("10"), cost=Decimal("6"),
        lead_time_days=None, safety_stock=None,
    )
    assert result.revenue_at_risk > 0
    assert result.gross_profit_at_risk > 0
    assert result.expected_recovery is None
    assert result.confidence == "LOW"


def test_calibrated_expected_recovery_uses_observed_rates():
    result = estimate_recovery(
        classification="DEAD", stock=Decimal("100"), cost=Decimal("10"), sell=Decimal("15"),
        calibration_rates=[Decimal("0.40"), Decimal("0.50"), Decimal("0.60")],
    )
    assert result.expected_recovery == Decimal("500.00")
    assert result.recoverable_low == Decimal("400.00")
    assert result.recoverable_high == Decimal("600.00")


def test_action_simulator_uses_observed_prices_and_labels_estimates():
    from app.services.recovery_intelligence import simulate_action_options
    options = simulate_action_options(
        action_type="discount", stock=Decimal("100"), cost=Decimal("10"), sell=Decimal("15"),
        historical_prices=[Decimal("12"), Decimal("15")],
    )
    assert options[0]["name"] == "DO NOTHING"
    assert any(o["name"] == "SELL AT OBSERVED LOW PRICE" for o in options)
    assert all(o["estimate_only"] for o in options)
