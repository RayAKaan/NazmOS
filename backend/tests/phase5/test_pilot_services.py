from app.services.ai_budget import AIBudget
from app.services.decision_explanation import build_explanation
from app.services.pilot_mode import PilotPolicy

def test_budget_caps_calls():
    b=AIBudget(daily_calls=2, per_audit_calls=2)
    b.begin_audit()
    assert b.can_call()
    b.record(success=True)
    assert b.can_call()
    b.record(success=True)
    assert not b.can_call()

def test_explanation_uses_evidence_not_financial_claims():
    x=build_explanation(decision="DO_NOTHING", evidence={"items":[{"sku":"A","current_stock":4,"daily_velocity":0}]})
    assert x["decision"] == "DO_NOTHING"
    assert x["financial_authority"] == "NazmOS deterministic financial engine"

def test_pilot_never_auto_executes_by_default():
    p=PilotPolicy(enabled=True, require_approval=True, allow_real_execution=False)
    assert p.disposition(execution_capable=True) == "APPROVAL_REQUIRED"
    assert p.disposition(execution_capable=False) == "MANUAL"
