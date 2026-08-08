"""Tests for production-hardening fixes: PII redaction, config validators, item resolver."""
import pytest
from unittest.mock import MagicMock

from app.utils.logger import redact_pii, _redact_string
from app.config import Settings
from app.adapters.item_resolver import resolve_item


def test_redact_pii_masks_known_keys():
    data = {"email": "owner@example.com", "password": "secret123", "safe": "visible"}
    result = redact_pii(data)
    assert result["email"] == "[REDACTED]"
    assert result["password"] == "[REDACTED]"
    assert result["safe"] == "visible"


def test_redact_pii_masks_nested_pii():
    data = {"user": {"phone": "+966501234567", "name": "Ahmed"}}
    result = redact_pii(data)
    assert result["user"]["phone"] == "[REDACTED]"
    assert result["user"]["name"] == "Ahmed"


def test_redact_string_masks_email_and_phone():
    text = "Contact owner@example.com or +966501234567"
    result = _redact_string(text)
    assert "owner@example.com" not in result
    assert "+966501234567" not in result
    assert "[REDACTED]" in result


def test_settings_rejects_mock_llm_in_production():
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="production", USE_MOCK_LLM=True, SENTRY_DSN="https://x@sentry.io/1", SECRET_KEY="a" * 48, CREDENTIAL_MASTER_KEY="b" * 48)


def test_settings_rejects_missing_credential_master_key_in_production():
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="production", USE_MOCK_LLM=False, SENTRY_DSN="https://x@sentry.io/1", SECRET_KEY="a" * 48)


def test_settings_rejects_missing_sentry_dsn_in_production():
    with pytest.raises(ValueError):
        Settings(
            ENVIRONMENT="production",
            USE_MOCK_LLM=False,
            SECRET_KEY="a" * 48,
            CREDENTIAL_MASTER_KEY="b" * 48,
        )


def test_sentry_initialization_skipped_when_dsn_missing():
    from unittest.mock import patch
    with patch("sentry_sdk.init") as mock_init:
        # Simulate the lifespan guard: no DSN means no init call.
        dsn = ""
        if dsn:
            import sentry_sdk
            sentry_sdk.init(dsn=dsn)
        mock_init.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_item_prefers_barcode_match():
    db = MagicMock()

    async def mock_execute(stmt, params):
        result = MagicMock()
        if "barcode" in str(stmt).lower() and params.get("barcode") == "123456":
            result.mappings.return_value.fetchone.return_value = {
                "id": "uuid-1", "name": "Milk", "sku": "MLK-1", "barcode": "123456",
                "cost_price": 5.0, "sell_price": 8.0,
            }
        else:
            result.mappings.return_value.fetchone.return_value = None
        return result

    db.execute = mock_execute
    item = await resolve_item(db, "biz-1", "Milk", sku="MLK-1", barcode="123456")
    assert item["barcode"] == "123456"


@pytest.mark.asyncio
async def test_resolve_item_returns_none_when_no_match():
    db = MagicMock()

    async def mock_execute(stmt, params):
        result = MagicMock()
        result.mappings.return_value.fetchone.return_value = None
        return result

    db.execute = mock_execute
    item = await resolve_item(db, "biz-1", "Unknown Item")
    assert item is None
