from app.services.pilot_mode import PilotPolicy
from app.services.pilot_readiness import _num

def test_pilot_policy_requires_approval_by_default():
    p=PilotPolicy()
    assert p.require_approval is True
    assert p.allow_real_execution is False

def test_numeric_normalization():
    assert _num(None)==0
    assert _num("12.5")==12.5
