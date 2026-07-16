from app.services.shariah_compliance import audit_inventory_halal_status, check_pricing_ethics_ihtikar


def test_haram_inventory_keyword_is_flagged():
    res = audit_inventory_halal_status([
        {"sku": "X", "name": "Cooking wine", "description": ""}
    ])
    assert res["status"] == "REVIEW_REQUIRED_PROHIBITED_KEYWORD"
    assert len(res["flagged_violations"]) == 1


def test_clean_inventory_passes_guardrails():
    res = audit_inventory_halal_status([
        {"sku": "DAT-SUK-01", "name": "Al-Qassim Sukari Dates 1kg", "description": "Premium dates"}
    ])
    assert res["status"] == "CLEAN_RETAIL_GUARDRAILS_PASSED"
    assert res["clean_items"] == 1


def test_ramadan_essential_price_hike_threshold_is_stricter():
    res = check_pricing_ethics_ihtikar(
        item_name="Sukari Dates 1kg",
        old_price=20,
        new_price=25,
        cost_increase_pct=2,
        is_ramadan=True,
    )
    assert res["ethical_status"] == "FLAGGED_IHTIKAR_RISK"


def test_non_essential_price_change_can_pass():
    res = check_pricing_ethics_ihtikar(
        item_name="Premium Ceramic Mug",
        old_price=20,
        new_price=25,
        cost_increase_pct=0,
        is_ramadan=True,
    )
    assert res["ethical_status"] == "APPROVED_ETHICAL_FAIR_TRADE"
