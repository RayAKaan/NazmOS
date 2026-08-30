import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, r'H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend')
from app.services.constraint_service import filter_action_with_code

def check(label, action, payload, constraints, expect_feasible, expect_code):
    ok, code, msg = filter_action_with_code(action, payload, constraints)
    status = "PASS" if (ok == expect_feasible and code == expect_code) else "FAIL"
    print(f"[{status}] {label}: feasible={ok} code={code} (want feasible={expect_feasible} code={expect_code})")
    return status == "PASS"

results = []

# --- DISCOUNT constraints ---
results.append(check("blocked discount product", "discount",
    {"item_id": "ITEM", "discount_pct": 10}, {"blocked_discount_products": ["ITEM"]},
    False, "CONSTRAINT_DISCOUNT_BLOCKED"))
results.append(check("strategic product no discount", "discount",
    {"item_id": "S", "discount_pct": 10}, {"strategic_products": ["S"]},
    False, "CONSTRAINT_DISCOUNT_STRATEGIC"))
results.append(check("discount exceeds max pct", "discount",
    {"item_id": "x", "discount_pct": 20, "sell_price_sar": 100, "cost_price_sar": 30},
    {"max_discount_pct": 15}, False, "CONSTRAINT_DISCOUNT_MAX_PCT"))
# margin must be >=20%: sell 100 cost 30, 10% discount -> 90 -> (90-30)/90=66.7% OK
results.append(check("healthy margin allows discount", "discount",
    {"item_id": "x", "discount_pct": 10, "sell_price_sar": 100, "cost_price_sar": 30},
    {"minimum_margin_pct": 20}, True, "CONSTRAINT_OK"))
# margin must be >=20%: sell 100 cost 60, 50% discount -> 50 -> (50-60)/50=-20% BLOCKED
results.append(check("min margin violated after discount", "discount",
    {"item_id": "x", "discount_pct": 50, "sell_price_sar": 100, "cost_price_sar": 60},
    {"minimum_margin_pct": 20}, False, "CONSTRAINT_DISCOUNT_MIN_MARGIN"))

# --- REORDER constraints (isolated dicts) ---
results.append(check("reorder exceeds cash budget", "reorder",
    {"estimated_cost_sar": 700}, {"cash_budget": 500},
    False, "CONSTRAINT_REORDER_CASH_BUDGET"))
results.append(check("reorder within max purchase", "reorder",
    {"estimated_cost_sar": 300}, {"cash_budget": 1000, "maximum_purchase_amount": 400},
    True, "CONSTRAINT_OK"))
results.append(check("reorder exceeds max purchase", "reorder",
    {"estimated_cost_sar": 300}, {"maximum_purchase_amount": 200},
    False, "CONSTRAINT_REORDER_MAX_PURCHASE"))
results.append(check("preferred supplier respected", "reorder",
    {"estimated_cost_sar": 100, "supplier_id": "A"}, {"supplier_preferences": ["A"]},
    True, "CONSTRAINT_OK"))
results.append(check("non-preferred supplier rejected", "reorder",
    {"estimated_cost_sar": 100, "supplier_id": "B"}, {"supplier_preferences": ["A"]},
    False, "CONSTRAINT_REORDER_SUPPLIER_PREFERENCE"))
results.append(check("min safety stock enforced", "reorder",
    {"estimated_cost_sar": 50, "quantity": 5, "current_stock": 2}, {"minimum_safety_stock": 10},
    False, "CONSTRAINT_REORDER_MIN_SAFETY"))

# --- TRANSFER constraints ---
results.append(check("transfer route blocked", "transfer_inventory",
    {"from_business_id": "b1", "to_business_id": "b2"}, {"blocked_transfer_routes": ["b1->b2"]},
    False, "CONSTRAINT_TRANSFER_ROUTE"))

# --- No constraints -> everything feasible ---
results.append(check("no constraints -> discount OK", "discount",
    {"item_id": "x", "discount_pct": 50, "sell_price_sar": 100, "cost_price_sar": 60},
    {}, True, "CONSTRAINT_OK"))

passed = sum(results)
print(f"\nCONSTRAINT CHECKS: {passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
