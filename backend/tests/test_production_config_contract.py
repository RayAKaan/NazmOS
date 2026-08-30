"""WS7 — production configuration contract.

Pins every production-only config gate so the deploy matrix is explicit and a
config drift (e.g. someone enabling SQLite in prod, or dropping the RLS app
role) fails at Settings() construction, not at runtime under load.
"""
import pytest

from app.config import Settings


_PG_URL = "postgresql+asyncpg://u:p@localhost:5432/nazmos"
_LLM = {"GROQ_API_KEY": "grok-test-key"}


def _prod(**overrides):
    base = {
        "ENVIRONMENT": "production",
        "USE_MOCK_LLM": False,
        "SENTRY_DSN": "https://x@sentry.io/1",
        "SECRET_KEY": "a" * 48,
        "CREDENTIAL_MASTER_KEY": "b" * 48,
        "DATABASE_APP_ROLE": "nazmos_app",
        "DATABASE_URL": _PG_URL,
        **_LLM,
    }
    base.update(overrides)
    return Settings(**base)


def test_production_requires_database_app_role():
    with pytest.raises(ValueError, match="DATABASE_APP_ROLE is required"):
        _prod(DATABASE_APP_ROLE="")


def test_production_forbids_sqlite_database():
    with pytest.raises(ValueError, match="SQLite is not allowed in production"):
        _prod(DATABASE_URL="sqlite+aiosqlite:///./nazmos.db")


def test_production_given_full_matching_config_constructs():
    s = _prod()
    assert s.ENVIRONMENT == "production"
    assert s.DATABASE_APP_ROLE == "nazmos_app"
    assert not s.USE_MOCK_LLM


def test_production_forbids_cors_wildcard():
    with pytest.raises(ValueError, match="CORS wildcard"):
        _prod(CORS_ORIGINS="*")


def test_production_forbids_cors_origin_without_scheme():
    with pytest.raises(ValueError, match="scheme"):
        _prod(CORS_ORIGINS="https://app.nazmos.com,app.other.com")


def test_production_requires_at_least_one_llm_provider():
    with pytest.raises(ValueError, match="GROQ_API_KEY or GOOGLE_AI_API_KEY"):
        _prod(GROQ_API_KEY="", GOOGLE_AI_API_KEY="")


def test_production_live_whatsapp_requires_token_and_phone_id():
    with pytest.raises(ValueError, match="WHATSAPP_ENABLED=live"):
        _prod(WHATSAPP_ENABLED="live", WHATSAPP_TOKEN="", WHATSAPP_PHONE_ID="")


def test_sqlite_mode_still_allowed_outside_production():
    Settings(DATABASE_URL="sqlite+aiosqlite:///./dev.db")



def test_production_weak_dev_secret_key_blocked_at_get_settings():
    """get_settings() FATAL gates (dev secret key, missing SENTRY_DSN, mock LLM,
    missing master key) are independent of Settings() validation."""
    import os
    from unittest.mock import patch

    import app.config as config_mod
    from app.config import get_settings

    keys = ("ENVIRONMENT", "SECRET_KEY", "SENTRY_DSN", "USE_MOCK_LLM",
            "CREDENTIAL_MASTER_KEY", "GROQ_API_KEY", "GOOGLE_AI_API_KEY",
            "DATABASE_APP_ROLE", "DATABASE_URL", "REDIS_URL", "UPLOAD_DIR",
            "LLM_PROVIDER_ORDER", "WHATSAPP_ENABLED", "CORS_ORIGINS")
    saved = {k: os.environ.get(k) for k in keys}
    env = {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "dev-secret-key-change-me",
        "SENTRY_DSN": "https://x@sentry.io/1",
        "USE_MOCK_LLM": "false",
        "CREDENTIAL_MASTER_KEY": "b" * 48,
        "GROQ_API_KEY": "grok-test-key",
        "DATABASE_APP_ROLE": "nazmos_app",
        "DATABASE_URL": _PG_URL,
    }
    try:
        for k in keys:
            os.environ.pop(k, None)
        os.environ.update(env)
        config_mod.get_settings.cache_clear()
        with pytest.raises(RuntimeError, match="dev default"):
            get_settings()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config_mod.get_settings.cache_clear()