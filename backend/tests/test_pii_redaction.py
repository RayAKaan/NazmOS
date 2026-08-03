"""Tests for PII redaction in structured logs."""
import json

import pytest

from app.utils.logger import redact_pii, _REDACTED


@pytest.mark.parametrize(
    "key,value",
    [
        ("password", "super-secret"),
        ("email", "merchant@example.com"),
        ("phone", "+966501234567"),
        ("api_key", "sk-1234567890abcdef"),
        ("token", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"),
    ],
)
def test_redact_pii_top_level(key, value):
    result = redact_pii({key: value, "safe": "visible"})
    assert result[key] == _REDACTED
    assert result["safe"] == "visible"


def test_redact_pii_nested():
    payload = {"user": {"email": "nested@example.com", "name": "Safe Name"}}
    result = redact_pii(payload)
    assert result["user"]["email"] == _REDACTED
    assert result["user"]["name"] == "Safe Name"


def test_redact_pii_in_list():
    payload = {"items": [{"password": "x"}, {"password": "y"}]}
    result = redact_pii(payload)
    assert result["items"][0]["password"] == _REDACTED
    assert result["items"][1]["password"] == _REDACTED


def test_json_formatter_redacts_pii():
    from app.utils.logger import JSONFormatter
    import logging

    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Login attempt",
        args=(),
        exc_info=None,
    )
    record.email = "secret@example.com"
    record.safe = "visible"
    formatted = json.loads(formatter.format(record))
    assert formatted["email"] == _REDACTED
    assert formatted["safe"] == "visible"
