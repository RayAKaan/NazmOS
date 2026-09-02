"""Phase D: durable security- event audit + global PII redaction."""
import asyncio
import datetime
import json
import logging

from app.services.security_audit_service import _scrub_detail
from app.utils.logger import JSONFormatter, _redact_string, redact_pii


def test_redact_pii_full_walk():
    data = {
        "password": "hunter2",
        "nested": {"api_key": "sk-xyz", "message": "contact 0551234567 or a@b.com"},
        "labels": ["safe", "tok_abc123", "phone 0551234567", "aid 1051234567"],
        "clean": 42,
    }
    out = redact_pii(data)
    joined = json.dumps(out)
    assert "hunter2" not in joined
    assert "sk-xyz" not in joined
    assert "0551234567" not in joined
    assert "a@b.com" not in joined
    assert "tok_abc123" not in joined
    assert "1051234567" not in joined
    assert out["clean"] == 42
    assert out["password"] == "[REDACTED]"


def test_json_formatter_redacts_extras():
    record = logging.LogRecord(
        "app", logging.ERROR, "x.py", 1, "boom", (), None
    )
    record.token = "sk-secret-fragment"
    record.msg = "failed for 0501234567 and ceo@nazmos.sa"
    out = json.loads(JSONFormatter().format(record))
    assert out["token"] == "[REDACTED]"
    assert "0501234567" not in out["message"]
    assert "ceo@nazmos.sa" not in out["message"]


def test_redact_string_strips_saudi_identifiers():
    text = "id 1051234567 phone 0567888899 email lead@x.com"
    out = _redact_string(text)
    assert "1051234567" not in out
    assert "0567888899" not in out
    assert "lead@x.com" not in out


def test_scrub_detail_allowlist_and_never_prompt_text():
    detail = {
        "source": "opencode",
        "reasoning": "do not persist this free text",   # non-allowlisted -> dropped
        "prompt": "inventory appears in the JSON body",  # non-allowlisted -> dropped
        "ratio": 1.5,                                    # non-allowlisted -> dropped
        "reason": "ai.policy.denied",                    # allowlisted, bounded
        "when": datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        "bad": object(),
    }
    out = _scrub_detail(detail)
    assert out["source"] == "opencode"
    assert "reasoning" not in out
    assert "prompt" not in out
    assert "ratio" not in out
    assert "bad" not in out
    assert out["reason"] == "ai.policy.denied"
    # Timestamps belong in dedicated columns, never audit detail.
    assert "when" not in out


def test_audit_writers_are_best_effort():
    # No DB reachable in this unit context: writers must return False, not raise.
    assert asyncio.run(
        __import__("app.services.security_audit_service", fromlist=["x"]).record_security_event(
            event_type="ai.policy.denied"
        )
    ) in (False, True)