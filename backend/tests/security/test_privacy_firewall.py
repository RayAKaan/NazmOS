"""Privacy firewall: raw merchant data never survives into a capsule/prompt."""
import json

from app.services.evidence_package import BusinessContext, ItemEvidence

from app.security.capsule import CapsuleSigner
from app.security.privacy_firewall import (
    build_capsule_for_payload,
    build_reasoning_capsule,
)

# Distinctive tokens -- any of these appearing in a capsule/prompt is a leak.
SKU = "SKU-1001-XYZ"
PRODUCT = "Premium Dates Gift Box"
SUPPLIER = "Al-Nakhil Trading Co"
BUSINESS = "515769a5-519f-437f-a906-a408f438202c"


def _item() -> ItemEvidence:
    return ItemEvidence(
        sku=SKU,
        product_name=PRODUCT,
        classification="slow_mover",
        current_stock=1234.0,
        cost_price_sar=44.5,
        sell_price_sar=99.9,
        inventory_value_sar=123456.75,
        recent_velocity_per_day=0.2,
        prior_velocity_per_day=0.5,
        daily_velocity=0.2,
        days_of_supply=250.0,
        days_since_last_sale=40,
        inventory_age_days=300,
        monthly_concentration_peak=0.62,
        confirmed_inbound_qty=0,
        supplier_lead_time_days=14,
        supplier_moq=500.0,
        supplier_name=SUPPLIER,
        capital_at_risk_sar=123456.75,
        overstock_days=190,
        margin_pct=0.55,
        is_strategic=True,
        candidate_actions=["discount"],
    )


def _business() -> BusinessContext:
    return BusinessContext(
        business_id=BUSINESS,
        business_type="baqala",
        total_inventory_value_sar=5_000_000,
        total_capital_at_risk_sar=2_000_000,
        total_recoverable_high_sar=900_000,
        cash_budget=50_000,
        max_discount_pct=40,
        blocked_discount_products=[SKU],
        strategic_products=[SKU],
        minimum_margin_pct=0.10,
    )


def _capsule_text() -> str:
    capsule = build_reasoning_capsule(
        _item(), _business(), capability="counterfactual_audit", purpose="_internal"
    )
    CapsuleSigner().verify(capsule)
    return json.dumps(capsule.blob(), default=str)


def test_capsule_never_contains_identifiers():
    text = _capsule_text()
    assert SKU not in text
    assert PRODUCT not in text
    assert SUPPLIER not in text
    assert BUSINESS not in text


def test_capsule_never_contains_exact_financial_values():
    text = _capsule_text()
    assert "123456.75" not in text  # inventory value / capital at risk
    assert "44.5" not in text  # cost
    assert "99.9" not in text  # sell price
    assert "1234" not in text  # exact stock quantity
    assert "50000" not in text  # cash budget
    assert "2,000,000" not in text
    assert "0.62" not in text  # monthly concentration peak


def test_capsule_contains_derived_bands():
    capsule = build_reasoning_capsule(
        _item(), _business(), capability="counterfactual_audit", purpose="_internal"
    )
    item = capsule.items[0]
    assert item.stock_band == "500+"  # 1234 units -> band
    assert item.days_of_supply_band == "OVER"
    assert item.inventory_age_band == "OLD"
    assert item.monthly_concentration_band == "HIGH"
    assert item.margin_band == "HIGH"
    assert item.supplier_lead_time_band == "MEDIUM"
    assert item.is_strategic is True
    assert "REORDER" not in item.candidate_decisions
    assert "DISCOUNT" in item.candidate_decisions


def test_derived_signal_fields_only():
    capsule = build_reasoning_capsule(
        _item(), _business(), capability="counterfactual_audit", purpose="_internal"
    )
    blob = capsule.blob()
    assert "sku" not in blob.get("items", [{}])[0]
    assert "current_stock" not in blob.get("items", [{}])[0]
    assert "cash_budget" not in blob.get("business", {})
    assert "business_id" not in blob.get("business", {})


def test_payload_path_also_sanitized():
    payload = {
        "items": [{
            "sku": SKU,
            "product_name": PRODUCT,
            "current_stock": 900,
            "cost_price_sar": 1.5,
            "sell_price_sar": 3.0,
            "inventory_value_sar": 1350,
            "recent_velocity_per_day": 0.1,
            "prior_velocity_per_day": 0.2,
            "daily_velocity": 0.1,
            "candidate_actions": ["transfer", "restock"],
        }],
        "business": {
            "business_id": BUSINESS,
            "total_capital_at_risk_sar": 500_000,
            "cash_budget": 12_500,
            "blocked_discount_products": [SKU],
        },
    }
    capsule = build_capsule_for_payload(payload, capability="opencode_brain", purpose="_internal")
    text = json.dumps(capsule.blob(), default=str)
    assert SKU not in text
    assert PRODUCT not in text
    assert BUSINESS not in text
    assert "1350" not in text
    assert "12500" not in text
    # Blocked SKU mapped to an opaque ref, never the SKU itself.
    assert capsule.constraints.blocked_refs == ["item_A"]
    # Both candidates from the trusted engine preserved.
    assert set(capsule.items[0].candidate_decisions) == {"TRANSFER", "REORDER"}


def test_capsule_is_signed():
    capsule = build_reasoning_capsule(
        _item(), _business(), capability="counterfactual_audit", purpose="_internal"
    )
    assert capsule.capsule_hash
    assert capsule.signature
    assert CapsuleSigner().verify(capsule) is True