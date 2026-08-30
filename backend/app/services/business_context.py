"""V11 Business Context Engine.

Converts raw database state into structured contextual evidence
for the AI Challenge Layer. This is the Context Engine for V11.

Provides: Product + Seasonal + Supplier + Promotion + Owner + Business + Time
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.services.evidence_package import ItemEvidence, BusinessContext
from app.services.ab_decision_framework import deterministic_decision_for_item
from app.utils.saudi_holidays import get_next_festival, SAUDI_HOLIDAYS_DF

logger = logging.getLogger(__name__)


@dataclass
class ProductContext:
    """Product-level context for AI challenge."""
    sku: str
    product_name: str
    category: str
    current_stock: float
    inventory_value_sar: float
    cost: float
    sell_price: float
    gross_margin_pct: float
    recent_velocity: float
    prior_velocity: float
    long_term_velocity: float
    trend: str  # "accelerating" | "stable" | "declining" | "flat"
    days_of_supply: float | None
    inventory_age_days: int | None
    last_sale_days_ago: int | None
    sales_frequency: str  # "daily" | "weekly" | "monthly" | "rare" | "never"
    demand_volatility: float

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class SeasonalContext:
    """Seasonal context for AI challenge."""
    is_seasonal: bool
    seasonal_type: str | None
    days_until_season: int | None
    days_since_season_ended: int | None
    historical_seasonal_demand_multiplier: float | None
    expected_seasonal_demand: float | None
    seasonal_confidence: float
    upcoming_seasons: list[dict]

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class SupplierContext:
    """Supplier context for AI challenge."""
    supplier_name: str | None
    lead_time_days: int | None
    on_time_pct: float | None
    moq_sar: float | None
    supplier_reliability: str  # "reliable" | "unreliable" | "unknown"
    confirmed_inbound_qty: float
    ghost_po_risk: bool
    preferred_supplier: bool

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class PromotionContext:
    """Promotion context for AI challenge."""
    is_promotional: bool
    promotion_type: str | None
    promotion_duration_days: int | None
    promotional_uplift_pct: float | None
    normal_velocity: float
    post_promotion_risk: bool

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class OwnerContext:
    """Owner constraint context for AI challenge."""
    cash_budget: float | None
    max_purchase_amount: float | None
    min_margin_pct: float | None
    max_discount_pct: float | None
    blocked_discount_skus: list[str]
    strategic_skus: list[str]
    blocked_transfer_routes: list[str]
    branch_priorities: list[str]
    risk_preference: str  # "conservative" | "balanced" | "aggressive"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class BusinessAggContext:
    """Business-level aggregate context."""
    business_type: str
    branch_count: int
    total_inventory_value_sar: float
    total_capital_at_risk_sar: float
    total_recoverable_sar: float
    recent_actions: list[dict]
    recent_outcomes: list[dict]

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class TimeContext:
    """Time/calendar context for AI challenge."""
    virtual_date: str
    day_of_week: str
    upcoming_holidays: list[dict]
    days_until_ramadan: int | None
    days_until_eid: int | None
    days_until_white_friday: int | None
    is_quarter_end: bool

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class StructuredContext:
    """Complete structured context for AI challenge."""
    product: ProductContext
    seasonal: SeasonalContext
    supplier: SupplierContext
    promotion: PromotionContext
    owner: OwnerContext
    business: BusinessAggContext
    time: TimeContext
    deterministic_decision: str
    deterministic_confidence: float
    ai_challenge_eligible: bool
    ai_challenge_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product.to_dict(),
            "seasonal": self.seasonal.to_dict(),
            "supplier": self.supplier.to_dict(),
            "promotion": self.promotion.to_dict(),
            "owner": self.owner.to_dict(),
            "business": self.business.to_dict(),
            "time": self.time.to_dict(),
            "deterministic_decision": self.deterministic_decision,
            "deterministic_confidence": self.deterministic_confidence,
            "ai_challenge_eligible": self.ai_challenge_eligible,
            "ai_challenge_reason": self.ai_challenge_reason,
        }


class BusinessContextEngine:
    """Builds structured context for AI challenge from item evidence and business data."""

    async def build_context(
        self,
        item: ItemEvidence,
        business: BusinessContext,
        virtual_date: date,
        *,
        supplier_data: dict | None = None,
        branch_data: dict | None = None,
        historical_outcomes: list[dict] | None = None,
    ) -> StructuredContext:
        """Build complete structured context for one item."""
        product = self._build_product_context(item)
        seasonal = self._build_seasonal_context(item, virtual_date)
        supplier = self._build_supplier_context(item, supplier_data)
        promotion = self._build_promotion_context(item)
        owner = self._build_owner_context(business)
        business_agg = self._build_business_context(business, historical_outcomes)
        time = self._build_time_context(virtual_date)

        det_decision = deterministic_decision_for_item(item)
        det_confidence = self._estimate_det_confidence(item, det_decision)
        eligible, reason = self._check_challenge_eligibility(item, det_decision, det_confidence)

        return StructuredContext(
            product=product,
            seasonal=seasonal,
            supplier=supplier,
            promotion=promotion,
            owner=owner,
            business=business_agg,
            time=time,
            deterministic_decision=det_decision,
            deterministic_confidence=det_confidence,
            ai_challenge_eligible=eligible,
            ai_challenge_reason=reason,
        )

    def _build_product_context(self, item: ItemEvidence) -> ProductContext:
        """Build product context from item evidence."""
        # Determine trend
        trend = "stable"
        if item.prior_velocity_per_day > 0 and item.recent_velocity_per_day > 0:
            ratio = item.recent_velocity_per_day / max(item.prior_velocity_per_day, 0.01)
            if ratio > 1.2:
                trend = "accelerating"
            elif ratio < 0.8:
                trend = "declining"
        elif item.recent_velocity_per_day == 0 and item.prior_velocity_per_day > 0:
            trend = "flat"

        # Sales frequency
        sales_frequency = "never"
        if item.days_since_last_sale is not None:
            if item.days_since_last_sale <= 1:
                sales_frequency = "daily"
            elif item.days_since_last_sale <= 7:
                sales_frequency = "weekly"
            elif item.days_since_last_sale <= 30:
                sales_frequency = "monthly"
            else:
                sales_frequency = "rare"

        # Demand volatility (coefficient of variation)
        demand_volatility = 0.0
        if item.recent_velocity_per_day > 0 and item.prior_velocity_per_day > 0:
            mean_vel = (item.recent_velocity_per_day + item.prior_velocity_per_day) / 2
            std_vel = abs(item.recent_velocity_per_day - item.prior_velocity_per_day) / 2
            demand_volatility = std_vel / max(mean_vel, 0.01)

        # Long-term velocity (weighted average)
        long_term_velocity = (item.recent_velocity_per_day * 0.6 +
                              item.prior_velocity_per_day * 0.4)

        return ProductContext(
            sku=item.sku,
            product_name=item.product_name,
            category=item.classification,
            current_stock=item.current_stock,
            inventory_value_sar=item.inventory_value_sar,
            cost=item.cost_price_sar,
            sell_price=item.sell_price_sar,
            gross_margin_pct=item.margin_pct or 0.0,
            recent_velocity=item.recent_velocity_per_day,
            prior_velocity=item.prior_velocity_per_day,
            long_term_velocity=round(long_term_velocity, 4),
            trend=trend,
            days_of_supply=item.days_of_supply,
            inventory_age_days=item.inventory_age_days,
            last_sale_days_ago=item.days_since_last_sale,
            sales_frequency=sales_frequency,
            demand_volatility=round(demand_volatility, 4),
        )

    def _build_seasonal_context(self, item: ItemEvidence, virtual_date: date) -> SeasonalContext:
        """Build seasonal context from item evidence and holiday calendar."""
        is_seasonal = item.classification == "SEASONAL"
        seasonal_type = item.seasonal_type

        # Get upcoming seasons
        upcoming_seasons = []
        try:
            next_festival = get_next_festival(virtual_date)
            if next_festival:
                upcoming_seasons.append({
                    "name": next_festival["name"],
                    "date": next_festival["date"],
                    "days_away": next_festival["days_away"],
                    "expected_uplift_pct": next_festival.get("expected_uplift_pct", 0),
                })
        except Exception as e:
            logger.warning("Failed to get next festival: %s", e)

        # Days until season
        days_until_season = item.days_until_season
        if days_until_season is None and upcoming_seasons:
            days_until_season = upcoming_seasons[0].get("days_away")

        # Seasonal confidence based on monthly concentration
        seasonal_confidence = 0.0
        if item.monthly_concentration_peak:
            seasonal_confidence = min(1.0, item.monthly_concentration_peak)

        return SeasonalContext(
            is_seasonal=is_seasonal,
            seasonal_type=seasonal_type,
            days_until_season=days_until_season,
            days_since_season_ended=item.days_since_season_ended,
            historical_seasonal_demand_multiplier=item.historical_seasonal_multiplier,
            expected_seasonal_demand=None,
            seasonal_confidence=round(seasonal_confidence, 4),
            upcoming_seasons=upcoming_seasons,
        )

    def _build_supplier_context(self, item: ItemEvidence, supplier_data: dict | None) -> SupplierContext:
        """Build supplier context from item evidence and database data."""
        data = supplier_data or {}
        return SupplierContext(
            supplier_name=item.supplier_name,
            lead_time_days=item.supplier_lead_time_days,
            on_time_pct=data.get("on_time_pct"),
            moq_sar=item.supplier_moq,
            supplier_reliability=item.supplier_reliability or "unknown",
            confirmed_inbound_qty=item.confirmed_inbound_qty,
            ghost_po_risk=item.ghost_po_risk,
            preferred_supplier=data.get("preferred", False),
        )

    def _build_promotion_context(self, item: ItemEvidence) -> PromotionContext:
        """Build promotion context from item evidence."""
        return PromotionContext(
            is_promotional=item.is_promotional,
            promotion_type=None,
            promotion_duration_days=None,
            promotional_uplift_pct=item.promotion_uplift_pct,
            normal_velocity=item.normal_velocity or item.prior_velocity_per_day,
            post_promotion_risk=item.is_promotional and item.promotion_uplift_pct and item.promotion_uplift_pct > 50,
        )

    def _build_owner_context(self, business: BusinessContext) -> OwnerContext:
        """Build owner context from business constraints."""
        return OwnerContext(
            cash_budget=business.cash_budget,
            max_purchase_amount=None,
            min_margin_pct=business.minimum_margin_pct,
            max_discount_pct=business.max_discount_pct,
            blocked_discount_skus=business.blocked_discount_products,
            strategic_skus=business.strategic_products,
            blocked_transfer_routes=business.blocked_transfer_routes,
            branch_priorities=[],
            risk_preference="balanced",
        )

    def _build_business_context(
        self,
        business: BusinessContext,
        historical_outcomes: list[dict] | None,
    ) -> BusinessAggContext:
        """Build business aggregate context."""
        return BusinessAggContext(
            business_type=business.business_type,
            branch_count=1,
            total_inventory_value_sar=business.total_inventory_value_sar,
            total_capital_at_risk_sar=business.total_capital_at_risk_sar,
            total_recoverable_sar=business.total_recoverable_high_sar,
            recent_actions=business.previous_actions[-5:] if business.previous_actions else [],
            recent_outcomes=historical_outcomes[-5:] if historical_outcomes else [],
        )

    def _build_time_context(self, virtual_date: date) -> TimeContext:
        """Build time/calendar context."""
        days_until_ramadan = None
        days_until_eid = None
        days_until_white_friday = None

        try:
            next_festival = get_next_festival(virtual_date)
            if next_festival:
                name = next_festival.get("name", "").lower()
                days_away = next_festival.get("days_away", 0)
                if "ramadan" in name:
                    days_until_ramadan = days_away
                elif "eid" in name:
                    days_until_eid = days_away
                elif "white friday" in name or "friday" in name:
                    days_until_white_friday = days_away
        except Exception as e:
            logger.warning("Failed to compute holiday distances: %s", e)

        # Quarter end check
        is_quarter_end = virtual_date.month in (3, 6, 9, 12) and virtual_date.day >= 25

        return TimeContext(
            virtual_date=virtual_date.isoformat(),
            day_of_week=virtual_date.strftime("%A"),
            upcoming_holidays=[],
            days_until_ramadan=days_until_ramadan,
            days_until_eid=days_until_eid,
            days_until_white_friday=days_until_white_friday,
            is_quarter_end=is_quarter_end,
        )

    def _estimate_det_confidence(self, item: ItemEvidence, decision: str) -> float:
        """Estimate deterministic decision confidence based on evidence clarity."""
        cls = item.classification

        # Clear cases
        if cls == "DEAD" and decision == "DISCOUNT":
            return 0.95
        if cls == "FAST" and decision == "DO_NOTHING":
            return 0.90
        if cls == "NEW" and decision == "DO_NOTHING":
            return 0.85

        # Moderate cases
        if cls == "SEASONAL":
            return 0.70
        if cls == "SLOW MOVING":
            return 0.75

        # Ambiguous cases
        if cls == "UNKNOWN":
            return 0.50

        # Default
        return 0.65

    def _check_challenge_eligibility(
        self,
        item: ItemEvidence,
        decision: str,
        confidence: float,
    ) -> tuple[bool, str | None]:
        """Check if item is eligible for AI challenge."""
        # High confidence deterministic decisions — no challenge needed
        if confidence >= 0.90:
            return False, "Deterministic decision is high-confidence"

        # Clear cases — no challenge needed
        if item.classification == "DEAD" and decision == "DISCOUNT":
            return False, "Dead stock discount is deterministic"
        if item.classification == "FAST" and decision == "DO_NOTHING":
            return False, "Fast mover no-action is deterministic"

        # Seasonal items — challenge eligible
        if item.classification == "SEASONAL":
            return True, "Seasonal classification may miss timing or context"

        # UNKNOWN classification — challenge eligible
        if item.classification == "UNKNOWN":
            return True, "Unknown classification benefits from contextual challenge"

        # Slow moving — challenge eligible
        if item.classification == "SLOW MOVING":
            return True, "Slow moving may have transfer or seasonal opportunities"

        # High-value items — challenge eligible
        if item.inventory_value_sar > 5000:
            return True, "High-value item benefits from contextual challenge"

        # Items with declining velocity — challenge eligible
        if item.prior_velocity_per_day > 0 and item.recent_velocity_per_day > 0:
            decline = 1.0 - (item.recent_velocity_per_day / max(item.prior_velocity_per_day, 0.01))
            if decline > 0.3:
                return True, "Declining velocity benefits from contextual challenge"

        # Ghost PO risk — challenge eligible
        if item.ghost_po_risk:
            return True, "Ghost PO risk requires contextual validation"

        # Promotion distortion — challenge eligible
        if item.is_promotional and item.promotion_uplift_pct and item.promotion_uplift_pct > 30:
            return True, "Promotional distortion may affect decision"

        return False, None
