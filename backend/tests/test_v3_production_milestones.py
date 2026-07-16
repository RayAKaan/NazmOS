from app.services.shariah_compliance import audit_inventory_halal_status


def test_retail_recovery_guardrail_clean_item():
    res = audit_inventory_halal_status([
        {"sku": "WAT-330", "name": "Bottled Water Pack 330ml", "description": "Long shelf-life packaged water"}
    ])
    assert res["status"] == "CLEAN_RETAIL_GUARDRAILS_PASSED"


def test_retail_recovery_guardrail_flagged_item():
    res = audit_inventory_halal_status([
        {"sku": "BAD-001", "name": "Pork snack", "description": ""}
    ])
    assert res["status"] == "REVIEW_REQUIRED_PROHIBITED_KEYWORD"
