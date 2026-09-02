import asyncio
import json
from unittest.mock import patch

from app.security.capsule import CapsuleItem, CapsuleSigner, ReasoningCapsule
from app.services.opencode_brain import BrainStats, _parse_opencode_json_output, reason


def _capsule(items: list[CapsuleItem] | None = None, deterministic_decision: str = "REORDER") -> ReasoningCapsule:
    return CapsuleSigner().sign(
        ReasoningCapsule.new(
            capability="opencode_brain",
            purpose="_internal",
            items=items or [CapsuleItem(ref="item_A", candidate_decisions=[deterministic_decision])],
        )
    )


def test_parse_json_event_output():
    stdout = json.dumps({"type": "message", "message": {"role": "assistant", "content": '{"decision":"DO_NOTHING","confidence":0.9,"reasoning":"safe","evidence_ids":[],"risk_flags":[]}'}})
    assert '"decision":"DO_NOTHING"' in _parse_opencode_json_output(stdout)


def test_fallback_preserves_deterministic_decision_when_cli_missing():
    async def run():
        stats = BrainStats()
        capsule = _capsule(deterministic_decision="REORDER")
        with patch("app.services.opencode_brain._find_opencode_bin", return_value=None):
            result = await reason(capsule, deterministic_decision="REORDER", stats=stats)
        return result
    result = asyncio.run(run())
    assert result.source == "fallback"
    assert result.decision == "REORDER"
    assert result.decision != "DO_NOTHING"


def test_reason_rejects_raw_evidence_dict():
    """Phase A invariant: raw evidence dicts are a TypeError, not a silent pass."""
    async def run():
        try:
            await reason({"items": [], "business": {}})
        except TypeError:
            return True
        return False
    assert asyncio.run(run()) is True