"""DLP: outbound/inbound content scanning is fail-closed."""
import pytest

from app.security.dlp import DLP_RULES, DLPViolationError, DlpScanner


def _fake_api_key() -> str:
    return "sk-live-" + "A" * 32


def _fake_jwt() -> str:
    return "eyJhbGciOiJIUzI1NiJ9." + "A" * 40 + "." + "B" * 40


def test_clean_text_no_violations():
    scanner = DlpScanner()
    assert scanner.scan("stock_band: LOW, velocity: NONE, decision: DISCOUNT") == []


def test_email_detected():
    assert any(v.label == "EMAIL" for v in DlpScanner().scan("contact merchant@corp.example now"))


def test_uuid_detected():
    assert any(v.label == "UUID" for v in DlpScanner().scan("business 515769a5-519f-437f-a906-a408f438202c"))


def test_api_key_detected():
    assert any(v.label == "API_KEY_OPENAI" for v in DlpScanner().scan(_fake_api_key()))


def test_jwt_detected():
    assert any(v.label == "JWT" for v in DlpScanner().scan(_fake_jwt()))


def test_db_url_detected():
    assert any(v.label == "DB_URL" for v in DlpScanner().scan("use postgres://user:pass@host/db as the url"))


def test_private_key_detected():
    block = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAuvOFm\n-----END RSA PRIVATE KEY-----"
    assert any(v.label == "PRIVATE_KEY" for v in DlpScanner().scan(block))


def test_assert_clean_raises_on_secret():
    scanner = DlpScanner()
    with pytest.raises(DLPViolationError):
        scanner.assert_clean(f"reasoning looks fine {_fake_api_key()}", context="outbound_user")


def test_assert_clean_passes_on_safe():
    DlpScanner().assert_clean('{"decision":"DO_NOTHING"}', context="outbound_user")


def test_scan_object_recurses_into_nested():
    obj = {"a": {"b": ["row1", "email someone@example.com"]}, "c": _fake_jwt()}
    labels = {v.label for v in DlpScanner().scan_object(obj)}
    assert {"EMAIL", "JWT"} <= labels


def test_violation_sample_is_truncated():
    violations = DlpScanner().scan(_fake_jwt())
    assert all(len(v.sample) <= 40 for v in violations)


def test_rule_labels_are_non_empty():
    assert DLP_RULES
    labels = {label for label, _ in DLP_RULES}
    assert "UUID" in labels
    assert "DB_URL" in labels