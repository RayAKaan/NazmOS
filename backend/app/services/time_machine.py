"""V8 Business Time Machine — simulates do-nothing vs NazmOS recommendation.

Every result is explicitly labeled:
  SIMULATION / ESTIMATE

Never call simulated money ACTUAL RECOVERY.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Any


D = Decimal
ZERO = D("0")


@dataclass
class ItemTimeProjection:
    """Per-item projection for a single scenario."""
    sku: str
    product_name: str
    classification: str
    current_stock: float
    cost_price_sar: float
    sell_price_sar: float
    daily_velocity: float
    days_of_supply: float | None
    financial_impact_sar: float  # negative = loss, positive = recovery
    description: str


@dataclass
class TimeMachineScenario:
    """Result of a single scenario simulation."""
    label: str  # "DO NOTHING", "NAZMOS RECOMMENDATION", "CASH-FIRST"
    total_impact_sar: float
    items_affected: int
    item_details: list[ItemTimeProjection] = field(default_factory=list)
    estimated: bool = True  # Always True — this is a simulation

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "total_impact_sar": round(self.total_impact_sar, 2),
            "items_affected": self.items_affected,
            "estimated": self.estimated,
            "item_details": [asdict(i) for i in self.item_details],
        }


@dataclass
class TimeMachineResult:
    """Complete time machine comparison result."""
    horizon_days: int
    do_nothing: TimeMachineScenario
    nazmos_recommendation: TimeMachineScenario
    cash_first: TimeMachineScenario | None = None
    margin_first: TimeMachineScenario | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "horizon_days": self.horizon_days,
            "do_nothing": self.do_nothing.to_dict(),
            "nazmos_recommendation": self.nazmos_recommendation.to_dict(),
            "estimated": True,
            "label": "SIMULATION / ESTIMATE",
        }
        if self.cash_first:
            result["cash_first"] = self.cash_first.to_dict()
        if self.margin_first:
            result["margin_first"] = self.margin_first.to_dict()
        return result


def _project_item(
    *,
    sku: str,
    product_name: str,
    classification: str,
    stock: float,
    cost: float,
    sell: float,
    daily_velocity: float,
    days_of_supply: float | None,
    horizon_days: int,
    action_type: str,
    expected_recovery_low: float = 0,
    expected_recovery_high: float = 0,
) -> ItemTimeProjection:
    """Project a single item's financial impact over a time horizon."""
    if stock <= 0 or cost <= 0:
        return ItemTimeProjection(
            sku=sku, product_name=product_name, classification=classification,
            current_stock=stock, cost_price_sar=cost, sell_price_sar=sell,
            daily_velocity=daily_velocity, days_of_supply=days_of_supply,
            financial_impact_sar=0, description="No stock to project.",
        )

    # DO NOTHING projection
    if classification in {"DEAD", "SLOW MOVING"}:
        # Dead stock continues to decay — assume 10% further depreciation per 30 days
        decay_rate = Decimal(str(horizon_days)) / Decimal("30") * Decimal("0.10")
        depreciation = float(D(str(stock)) * D(str(cost)) * min(decay_rate, Decimal("0.50")))
        impact = -depreciation
        desc = f"Dead stock continues to depreciate. Estimated carrying cost: SAR {depreciation:,.0f}."
    elif classification == "FAST":
        # Fast-moving items: stockout risk if not reordered
        days_until_stockout = stock / daily_velocity if daily_velocity > 0 else 999
        if days_until_stockout < horizon_days:
            lost_revenue = (horizon_days - days_until_stockout) * daily_velocity * sell
            impact = -lost_revenue
            desc = f"Projected stockout in {days_until_stockout:.0f} days. Estimated lost revenue: SAR {lost_revenue:,.0f}."
        else:
            impact = 0
            desc = "Sufficient stock for the projection period."
    elif classification == "SEASONAL":
        # Seasonal: depends on whether we're in season
        impact = 0
        desc = "Seasonal item — impact depends on season timing."
    elif classification in {"OVERSTOCK", "STOCKOUT RISK"}:
        # Overstock: carrying cost; stockout: lost revenue
        if days_of_supply and days_of_supply > 45:
            surplus = max(0, stock - daily_velocity * 30) * cost
            impact = -(surplus * Decimal(str(horizon_days)) / Decimal("30") * Decimal("0.05"))
            impact = float(impact)
            desc = f"Excess inventory carrying cost over {horizon_days} days."
        else:
            impact = 0
            desc = "No significant impact projected."
    else:
        impact = 0
        desc = "No significant impact projected."

    return ItemTimeProjection(
        sku=sku, product_name=product_name, classification=classification,
        current_stock=stock, cost_price_sar=cost, sell_price_sar=sell,
        daily_velocity=daily_velocity, days_of_supply=days_of_supply,
        financial_impact_sar=round(impact, 2), description=desc,
    )


def simulate_time_machine(
    *,
    items: list[dict[str, Any]],
    horizon_days: int = 30,
) -> TimeMachineResult:
    """Simulate do-nothing vs NazmOS recommendation over a time horizon.

    Every result is explicitly labeled:
      SIMULATION / ESTIMATE

    This is NOT actual recovery.
    """
    do_nothing_items = []
    nazmos_items = []

    for item in items:
        sku = item.get("sku", "")
        product_name = item.get("product_name", "")
        classification = item.get("classification", "UNKNOWN")
        stock = float(item.get("current_stock", 0))
        cost = float(item.get("cost_price_sar", 0))
        sell = float(item.get("sell_price_sar", 0))
        daily_velocity = float(item.get("daily_velocity", 0))
        days_of_supply = item.get("days_of_supply")
        action_type = item.get("action_type", "DO_NOTHING")
        recoverable_low = float(item.get("recoverable_low_sar", 0))
        recoverable_high = float(item.get("recoverable_high_sar", 0))

        # DO NOTHING projection
        dn = _project_item(
            sku=sku, product_name=product_name, classification=classification,
            stock=stock, cost=cost, sell=sell,
            daily_velocity=daily_velocity, days_of_supply=days_of_supply,
            horizon_days=horizon_days, action_type="DO_NOTHING",
        )
        do_nothing_items.append(dn)

        # NAZMOS RECOMMENDATION projection
        if action_type in {"discount", "recovery_match"} and recoverable_high > 0:
            # Assume partial recovery at midpoint of range
            expected_recovery = (recoverable_low + recoverable_high) / 2
            # Spread recovery over horizon (assume action taken in first week)
            recovery_ratio = min(1.0, 7.0 / horizon_days) if horizon_days > 0 else 1.0
            nazmos_impact = expected_recovery * recovery_ratio
            nz = ItemTimeProjection(
                sku=sku, product_name=product_name, classification=classification,
                current_stock=stock, cost_price_sar=cost, sell_price_sar=sell,
                daily_velocity=daily_velocity, days_of_supply=days_of_supply,
                financial_impact_sar=round(nazmos_impact, 2),
                description=f"Estimated recovery from {action_type}: SAR {nazmos_impact:,.0f}.",
            )
        elif action_type == "reorder" and classification == "FAST":
            # Prevented stockout: value = revenue preserved
            days_until_stockout = stock / daily_velocity if daily_velocity > 0 else 999
            if days_until_stockout < horizon_days:
                preserved = (horizon_days - days_until_stockout) * daily_velocity * sell
                nz = ItemTimeProjection(
                    sku=sku, product_name=product_name, classification=classification,
                    current_stock=stock, cost_price_sar=cost, sell_price_sar=sell,
                    daily_velocity=daily_velocity, days_of_supply=days_of_supply,
                    financial_impact_sar=round(preserved, 2),
                    description=f"Stockout prevented. Estimated preserved revenue: SAR {preserved:,.0f}.",
                )
            else:
                nz = _project_item(
                    sku=sku, product_name=product_name, classification=classification,
                    stock=stock, cost=cost, sell=sell,
                    daily_velocity=daily_velocity, days_of_supply=days_of_supply,
                    horizon_days=horizon_days, action_type=action_type,
                )
        else:
            nz = _project_item(
                sku=sku, product_name=product_name, classification=classification,
                stock=stock, cost=cost, sell=sell,
                daily_velocity=daily_velocity, days_of_supply=days_of_supply,
                horizon_days=horizon_days, action_type=action_type,
            )
        nazmos_items.append(nz)

    do_nothing_total = sum(i.financial_impact_sar for i in do_nothing_items)
    nazmos_total = sum(i.financial_impact_sar for i in nazmos_items)

    # CASH-FIRST variant: prioritize items with highest recoverable cash
    cash_first_items = sorted(
        [i for i in nazmos_items if i.financial_impact_sar > 0],
        key=lambda x: x.financial_impact_sar,
        reverse=True,
    )
    cash_first_total = sum(i.financial_impact_sar for i in cash_first_items)

    # MARGIN-FIRST variant: prioritize items where margin is preserved
    margin_first_items = [i for i in nazmos_items if i.classification in {"FAST", "SEASONAL"}]
    margin_first_total = sum(i.financial_impact_sar for i in margin_first_items)

    return TimeMachineResult(
        horizon_days=horizon_days,
        do_nothing=TimeMachineScenario(
            label="DO NOTHING",
            total_impact_sar=round(do_nothing_total, 2),
            items_affected=len([i for i in do_nothing_items if i.financial_impact_sar != 0]),
            item_details=do_nothing_items,
        ),
        nazmos_recommendation=TimeMachineScenario(
            label="NAZMOS RECOMMENDATION",
            total_impact_sar=round(nazmos_total, 2),
            items_affected=len([i for i in nazmos_items if i.financial_impact_sar != 0]),
            item_details=nazmos_items,
        ),
        cash_first=TimeMachineScenario(
            label="CASH-FIRST",
            total_impact_sar=round(cash_first_total, 2),
            items_affected=len(cash_first_items),
            item_details=cash_first_items,
        ) if cash_first_items else None,
        margin_first=TimeMachineScenario(
            label="MARGIN-FIRST",
            total_impact_sar=round(margin_first_total, 2),
            items_affected=len(margin_first_items),
            item_details=margin_first_items,
        ) if margin_first_items else None,
    )
