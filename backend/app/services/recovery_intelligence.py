"""Conservative, evidence-first financial reasoning for Money Audit.

This module deliberately separates economic exposure from recoverable cash.  It
contains no LLM decisions and does not invent supplier or recovery assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Any, Iterable

D = Decimal
ZERO = D("0")
MONEY_Q = D("0.01")
TARGET_MARGIN = D("0.22")


def money(v: Any) -> D:
    try:
        return D(str(v or 0)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO


def pct(v: D) -> D:
    return (v * D("100")).quantize(D("0.01"), rounding=ROUND_HALF_UP)




@dataclass(frozen=True)
class FinancialImpact:
    amount: D
    type: str
    basis: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class RecoverableOpportunity:
    low: D
    high: D
    basis: str
    action_type: str | None
    confidence: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class ExpectedRecovery:
    amount: D
    calibration_source: str
    action_type: str
    confidence: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class ActualRecovery:
    amount: D
    measurement_window_days: int
    source: str

@dataclass
class FinancialEstimate:
    inventory_value: D = ZERO
    capital_at_risk: D = ZERO
    revenue_at_risk: D = ZERO
    gross_profit_at_risk: D = ZERO
    recoverable_low: D = ZERO
    recoverable_high: D = ZERO
    expected_recovery: D | None = None
    confidence: str = "INSUFFICIENT DATA"
    confidence_score: D = ZERO
    classification: str = "UNKNOWN"
    evidence: dict[str, Any] | None = None
    assumptions: list[str] | None = None

    def json(self) -> dict[str, Any]:
        result = asdict(self)
        for k, v in list(result.items()):
            if isinstance(v, Decimal):
                result[k] = float(v)
        return result

    # ── Canonical _sar aliases (FINANCIAL_VOCABULARY_ADR.md §5.1) ──────────
    @property
    def recoverable_low_sar(self) -> D:
        return self.recoverable_low

    @property
    def recoverable_high_sar(self) -> D:
        return self.recoverable_high

    @property
    def expected_recovery_sar(self) -> D | None:
        return self.expected_recovery

    @property
    def capital_at_risk_sar(self) -> D:
        return self.capital_at_risk


def classify_inventory(
    *,
    stock: D,
    recent_qty_30: D,
    prior_qty_30: D,
    days_since_last_sale: int | None,
    inventory_age_days: int | None,
    seasonal_index: D | None = None,
    product_age_days: int | None = None,
    monthly_concentrations: list[D] | None = None,
) -> str:
    """Conservative classification with velocity-first logic.

    Key V7 fixes:
    - Velocity-based classification runs BEFORE stock check (fixes slow items with stock=0)
    - Monthly concentration detects seasonal demand spikes (replaces inverted seasonal_index)
    - FAST label added for high-velocity items
    """
    if product_age_days is not None and product_age_days < 30:
        return "NEW"

    daily = recent_qty_30 / D("30") if recent_qty_30 > 0 else D("0")

    # Seasonal: detect demand spike via monthly concentration variance.
    # If one month dominates (>=60% of total sales across all months), it's seasonal.
    # Only applies to items currently selling (recent_qty_30 > 0) to avoid
    # misclassifying dead items that had seasonal sales before going dormant.
    if recent_qty_30 > 0 and monthly_concentrations and len(monthly_concentrations) >= 2:
        total = sum(max(m, D("0")) for m in monthly_concentrations)
        if total > 0:
            peak = max(monthly_concentrations)
            concentration = peak / total
            if concentration >= D("0.60"):
                return "SEASONAL"

    # Also support legacy seasonal_index for backward compatibility
    if seasonal_index is not None and seasonal_index >= D("1.5") and recent_qty_30 < prior_qty_30:
        return "SEASONAL"

    # Dead: no demand in recent period, 60+ days dormant (or never sold), no prior demand.
    # Items with zero transactions are DEAD if they have inventory.
    if recent_qty_30 <= 0:
        is_dormant = (days_since_last_sale is None) or (days_since_last_sale is not None and days_since_last_sale >= 60)
        if is_dormant and prior_qty_30 <= 0:
            return "DEAD"
        return "UNKNOWN"

    # Slow moving: out of stock with low-to-moderate velocity.
    # Items that sell but can't keep up with demand and are perpetually out of stock.
    if stock <= 0 and daily > 0 and daily < D("3"):
        return "SLOW MOVING"

    # Stock check (after velocity classification)
    if stock <= 0:
        return "HEALTHY"

    # Fast: in stock with good velocity
    if daily >= D("1"):
        return "FAST"

    return "HEALTHY"


def estimate_recovery(
    *,
    classification: str,
    stock: D,
    cost: D,
    sell: D,
    surplus_qty: D = ZERO,
    calibration_rates: Iterable[D] | None = None,
) -> FinancialEstimate:
    """Return evidence-bounded recovery, not a fabricated point estimate.

    Without observed outcomes, expected recovery remains None.  The range is
    bounded by realizable gross proceeds and cost basis rather than a hard-coded
    30/35/100% recovery percentage.
    """
    inventory_value = money(stock * cost)
    evidence: dict[str, Any] = {"stock_units": float(stock), "cost_per_unit_sar": float(cost), "sell_price_sar": float(sell)}
    assumptions: list[str] = []
    if calibration_rates:
        rates = [r for r in calibration_rates if r >= 0]
        if rates:
            rate = money(D(str(median([float(r) for r in rates]))))
            expected = money(inventory_value * rate)
            return FinancialEstimate(
                inventory_value=inventory_value,
                capital_at_risk=inventory_value,
                recoverable_low=money(inventory_value * min(rates)),
                recoverable_high=money(inventory_value * max(rates)),
                expected_recovery=expected,
                confidence="HIGH" if len(rates) >= 20 else "MEDIUM",
                confidence_score=D("0.85") if len(rates) >= 20 else D("0.70"),
                classification=classification,
                evidence={**evidence, "calibration_samples": len(rates)},
                assumptions=["Expected recovery is calibrated from observed completed outcomes."],
            )

    if classification in {"DEAD", "SLOW MOVING"} and stock > 0 and sell > 0:
        gross_proceeds = money(stock * sell)
        # Recoverable capital is bounded by the lower of current cost basis and
        # gross proceeds.  We do not assume a discount will magically convert to cash.
        upper = min(inventory_value, gross_proceeds)
        assumptions.append("No observed recovery outcomes are available; expected recovery is withheld.")
        assumptions.append("Upper bound is limited to current inventory cost basis and gross selling proceeds.")
        return FinancialEstimate(
            inventory_value=inventory_value,
            capital_at_risk=inventory_value,
            recoverable_low=ZERO,
            recoverable_high=money(upper),
            expected_recovery=None,
            confidence="LOW" if classification == "SLOW MOVING" else "MEDIUM",
            confidence_score=D("0.40") if classification == "SLOW MOVING" else D("0.55"),
            classification=classification,
            evidence=evidence,
            assumptions=assumptions,
        )

    if classification == "FAST":
        return FinancialEstimate(
            inventory_value=inventory_value,
            capital_at_risk=ZERO,
            recoverable_low=ZERO,
            recoverable_high=ZERO,
            expected_recovery=None,
            confidence="HIGH",
            confidence_score=D("0.90"),
            classification=classification,
            evidence=evidence,
            assumptions=["High-velocity item; no recovery action needed."],
        )

    if classification == "SEASONAL":
        return FinancialEstimate(
            inventory_value=inventory_value,
            capital_at_risk=ZERO,
            recoverable_low=ZERO,
            recoverable_high=ZERO,
            expected_recovery=None,
            confidence="INSUFFICIENT DATA",
            confidence_score=D("0.25"),
            classification=classification,
            evidence=evidence,
            assumptions=["Seasonal demand is present; no recovery action is recommended from dormancy alone."],
        )

    return FinancialEstimate(
        inventory_value=inventory_value,
        capital_at_risk=ZERO,
        recoverable_low=ZERO,
        recoverable_high=ZERO,
        expected_recovery=None,
        confidence="INSUFFICIENT DATA",
        confidence_score=D("0.25"),
        classification=classification,
        evidence=evidence,
        assumptions=["Insufficient evidence to estimate recoverable value."],
    )


def stockout_financials(
    *, stock: D, daily_velocity: D, sell: D, cost: D,
    lead_time_days: int | None, safety_stock: D | None = None,
    trend_multiplier: D = D("1"), horizon_days: D = D("7"),
) -> FinancialEstimate:
    if daily_velocity <= 0 or sell <= 0:
        return FinancialEstimate(classification="UNKNOWN", confidence="INSUFFICIENT DATA", confidence_score=D("0.20"))
    effective_daily = daily_velocity * max(D("0.5"), min(D("2"), trend_multiplier))
    days_left = stock / effective_daily if stock > 0 else ZERO
    horizon = D(str(lead_time_days)) if lead_time_days is not None else horizon_days
    revenue = money(max(ZERO, (effective_daily * horizon) - stock) * sell)
    margin = money(max(ZERO, sell - cost) * max(ZERO, (effective_daily * horizon) - stock))
    conf = D("0.80") if lead_time_days is not None else D("0.45")
    return FinancialEstimate(
        revenue_at_risk=revenue,
        gross_profit_at_risk=margin,
        confidence="HIGH" if lead_time_days is not None else "LOW",
        confidence_score=conf,
        classification="STOCKOUT RISK",
        evidence={
            "current_stock": float(stock),
            "daily_velocity": float(effective_daily),
            "days_left": float(days_left),
            "lead_time_days": lead_time_days,
            "safety_stock": float(safety_stock) if safety_stock is not None else None,
        },
        assumptions=["Revenue at risk is projected demand, not cash recovered."] + (["Supplier lead time unavailable; horizon is limited to a seven-day exposure window."] if lead_time_days is None else []),
    )


def simulate_action_options(
    *,
    action_type: str,
    stock: D,
    cost: D,
    sell: D,
    historical_prices: list[D] | None = None,
    branch_demand_units: D | None = None,
) -> list[dict[str, Any]]:
    """Generate transparent scenarios from observed values only.

    No scenario is a guarantee.  Transfer is only offered when another branch's
    demand is explicitly supplied; discounts use observed historical prices when
    available instead of a hard-coded discount percentage.
    """
    options = [{"name": "DO NOTHING", "expected_recovery_sar": ZERO, "low_sar": ZERO, "high_sar": ZERO, "confidence": "HIGH", "estimate_only": True}]
    if action_type in {"discount", "recovery_match"} and stock > 0 and cost > 0 and historical_prices:
        prices = sorted([money(p) for p in historical_prices if p > 0])
        if prices:
            observed_low = prices[0]
            observed_median = money(D(str(median([float(p) for p in prices]))))
            low = min(money(stock * observed_low), money(stock * cost))
            high = min(money(stock * observed_median), money(stock * cost))
            options.append({"name": "SELL AT OBSERVED LOW PRICE", "expected_recovery_sar": None, "low_sar": low, "high_sar": high, "confidence": "MEDIUM", "estimate_only": True, "evidence": {"observed_low_price_sar": float(observed_low), "observed_median_price_sar": float(observed_median), "price_observations": len(prices)}})
    if branch_demand_units is not None and branch_demand_units > 0:
        transferable = min(stock, branch_demand_units)
        value = min(money(transferable * sell), money(transferable * cost))
        options.append({"name": "TRANSFER", "expected_recovery_sar": None, "low_sar": ZERO, "high_sar": value, "confidence": "MEDIUM", "estimate_only": True, "evidence": {"destination_demand_units": float(branch_demand_units), "transferable_units": float(transferable)}})
    return options
