"""Data classification policy for NazmOS.

Declarative registry of what merchant data is sensitive and how it must be
handled when it crosses the trusted-application boundary. This module only
*publishes the policy*; ``privacy_firewall.py`` enforces it when building the
ReasoningCapsule, and ``dlp.py`` enforces it on the outbound wire.

Severity levels (higher = tighter handling):
    PUBLIC      – safe to log/return to any authenticated surface.
    INTERNAL    – safe inside the trusted zone only.
    BUSINESS    – merchant business signals; may be shown to the merchant.
    SENSITIVE   – merchant operational data; MUST be banded/derived outside the
                  trusted zone and MUST NOT reach an LLM or OpenCode.
    RESTRICTED  – credentials/personal data; MUST never reach an LLM or
                  OpenCode in any form, never plaintext at rest.
"""
from __future__ import annotations

from enum import Enum


class DataClass(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    BUSINESS = "BUSINESS"
    SENSITIVE = "SENSITIVE"
    RESTRICTED = "RESTRICTED"


# Source field -> classification for the canonical evidence model shapes used
# by the AI path (ItemEvidence, BusinessContext, StructuredContext sections).
SENSITIVE_FIELDS: dict[str, DataClass] = {
    # Identity / entity references (never leave the trusted zone).
    "business_id": DataClass.RESTRICTED,
    "sku": DataClass.SENSITIVE,
    "product_name": DataClass.SENSITIVE,
    "supplier_name": DataClass.SENSITIVE,
    "blocked_discount_products": DataClass.SENSITIVE,
    "strategic_products": DataClass.SENSITIVE,
    "blocked_discount_skus": DataClass.SENSITIVE,
    "strategic_skus": DataClass.SENSITIVE,
    "blocked_transfer_routes": DataClass.SENSITIVE,
    "branch_priorities": DataClass.SENSITIVE,
    "recent_actions": DataClass.SENSITIVE,
    "recent_outcomes": DataClass.SENSITIVE,
    # Exact financial values (never leave the trusted zone).
    "current_stock": DataClass.SENSITIVE,
    "cost_price_sar": DataClass.SENSITIVE,
    "sell_price_sar": DataClass.SENSITIVE,
    "inventory_value_sar": DataClass.SENSITIVE,
    "capital_at_risk_sar": DataClass.SENSITIVE,
    "revenue_at_risk_sar": DataClass.SENSITIVE,
    "gross_profit_at_risk_sar": DataClass.SENSITIVE,
    "recoverable_low_sar": DataClass.SENSITIVE,
    "recoverable_high_sar": DataClass.SENSITIVE,
    "expected_recovery_sar": DataClass.SENSITIVE,
    "cash_budget": DataClass.SENSITIVE,
    "moq_sar": DataClass.SENSITIVE,
    "max_purchase_amount": DataClass.SENSITIVE,
    "total_inventory_value_sar": DataClass.SENSITIVE,
    "total_capital_at_risk_sar": DataClass.SENSITIVE,
    "total_recoverable_sar": DataClass.SENSITIVE,
    "total_recoverable_high_sar": DataClass.SENSITIVE,
    "historical_seasonal_demand_multiplier": DataClass.SENSITIVE,
    "expected_seasonal_demand": DataClass.SENSITIVE,
    "promotional_uplift_pct": DataClass.SENSITIVE,
    "margin_pct": DataClass.SENSITIVE,
    "gross_margin_pct": DataClass.SENSITIVE,
    "min_margin_pct": DataClass.SENSITIVE,
    "max_discount_pct": DataClass.SENSITIVE,
    "moq": DataClass.SENSITIVE,
    "confirmed_inbound_qty": DataClass.SENSITIVE,
    "monthly_concentrations": DataClass.SENSITIVE,
    "historical_outcomes": DataClass.SENSITIVE,
    "previous_actions": DataClass.SENSITIVE,
    "previous_outcomes": DataClass.SENSITIVE,
}

# Fields that are safe to send to an LLM as *derived banded signals*.
DERIVED_SIGNALS = frozenset({
    "classification",
    "stock_band",
    "velocity_band",
    "days_of_supply_band",
    "is_overstock",
    "is_stockout_risk",
    "inventory_age_band",
    "last_sale_band",
    "is_seasonal",
    "seasonal_type",
    "days_until_season",
    "trend",
    "sales_frequency_band",
    "demand_volatility_band",
    "margin_band",
    "supplier_reliability_band",
    "supplier_lead_time_band",
    "inbound_band",
    "is_strategic",
    "is_promotional",
    "promotion_type",
    "monthly_concentration_band",
    "candidate_decisions",
    "business_type",
    "branch_count",
    "capital_at_risk_band",
    "cash_available",
    "max_discount_band",
    "min_margin_band",
    "blocked_refs",
    "transfer_allowed",
    "deterministic_decision",
    "deterministic_confidence",
})

# Confidence / guard rails for each severity level crossing the boundary.
OUTBOUND_RULES: dict[DataClass, str] = {
    DataClass.RESTRICTED: "BLOCK",
    DataClass.SENSITIVE: "BLOCK",
    DataClass.BUSINESS: "ALLOW_DERIVED_ONLY",
    DataClass.INTERNAL: "ALLOW",
    DataClass.PUBLIC: "ALLOW",
}


def classify_field(field_name: str) -> DataClass:
    """Return the classification of a single field name (case-insensitive)."""
    return SENSITIVE_FIELDS.get(field_name, DataClass.INTERNAL)