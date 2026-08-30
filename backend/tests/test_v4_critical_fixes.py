import pytest
from decimal import Decimal
from app.services.recovery_intelligence import FinancialImpact, RecoverableOpportunity, ExpectedRecovery, ActualRecovery
from app.services.action_registry import can_execute, get_action_spec
from app.services.constraint_service import filter_action
from app.services.data_normalizer import normalize_dataframe, DataQualityError
from app.utils.clock import set_virtual_now, utcnow, advance_days, reset_virtual_now
import pandas as pd
from datetime import datetime, timezone

def test_financial_types_are_distinct():
    impact=FinancialImpact(Decimal("100"), "REVENUE_AT_RISK", "projected_sales", {})
    opp=RecoverableOpportunity(Decimal("0"), Decimal("50"), "action_bound", "discount", "LOW", {})
    exp=ExpectedRecovery(Decimal("25"), "discount:20", "discount", "MEDIUM", {})
    actual=ActualRecovery(Decimal("20"), 30, "measured_sales")
    assert impact.amount != exp.amount
    assert opp.action_type != actual.source
    assert all(hasattr(x, "evidence") for x in (impact, opp, exp))

def test_action_registry_does_not_fake_manual_actions():
    assert get_action_spec("discount").can_execute is False
    assert can_execute("discount", {"item_id":"1"}) is False
    assert can_execute("discount", {"item_id":"1", "suggested_price":8}) is True
    assert can_execute("recovery_match", {"item_id":"1"}) is False
    assert can_execute("recovery_match", {"item_id":"1","from_business_id":"a","to_business_id":"b","quantity":2}) is True

def test_constraints_filter_before_approval():
    constraints={"cash_budget":1000,"max_discount":5,"blocked_discount_products":["p1"],"blocked_transfer_routes":["a->b"]}
    assert filter_action("discount", {"item_id":"p1","discount_pct":2}, constraints)[0] is False
    assert filter_action("reorder", {"estimated_cost_sar":1001}, constraints)[0] is False
    assert filter_action("transfer_inventory", {"from_business_id":"a","to_business_id":"b","quantity":1}, constraints)[0] is False

def test_virtual_clock_changes_business_time():
    base=datetime(2026,8,24,tzinfo=timezone.utc)
    set_virtual_now(base)
    assert utcnow()==base
    assert advance_days(10).date().isoformat()=="2026-09-03"
    reset_virtual_now()

def test_strict_normalization_rejects_financial_bad_rows():
    df=pd.DataFrame({"item_name":["A","B"],"quantity":[1,-2],"unit_price":[10,20],"transaction_at":["2026-08-24","bad"]})
    with pytest.raises(DataQualityError):
        normalize_dataframe(df,{"item_name":"item_name","quantity":"quantity","unit_price":"unit_price","transaction_at":"transaction_at"},strict=True)
