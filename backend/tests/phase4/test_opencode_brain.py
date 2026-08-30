import asyncio
import json
from unittest.mock import patch

from app.services.opencode_brain import BrainStats, _parse_opencode_json_output, reason


def test_parse_json_event_output():
    stdout = json.dumps({"type": "message", "message": {"role": "assistant", "content": '{"decision":"DO_NOTHING","confidence":0.9,"reasoning":"safe","evidence_ids":[],"risk_flags":[]}'}})
    assert '"decision":"DO_NOTHING"' in _parse_opencode_json_output(stdout)


def test_fallback_preserves_deterministic_decision_when_cli_missing():
    async def run():
        stats = BrainStats()
        with patch("app.services.opencode_brain._find_opencode_bin", return_value=None):
            result = await reason({"items": [], "business": {}}, deterministic_decision="REORDER", stats=stats)
        return result
    result = asyncio.run(run())
    assert result.source == "fallback"
    assert result.decision == "REORDER"
    assert result.decision != "DO_NOTHING"
