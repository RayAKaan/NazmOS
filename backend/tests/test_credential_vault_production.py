"""Tests for Phase 3.1: secrets/deploy hardening.

1. ``CredentialVault`` keeps its fixed salt but fails fast in production when
   ``CREDENTIAL_MASTER_KEY`` is not set (per-install key only, no dev fallback).
   In development the dev fallback key still works so tests/zero-cost runs work.
2. ``Settings`` rejects a production config that omits ``DATABASE_APP_ROLE``
   (required for RLS enforcement) while development still defaults to "".
"""
import os

import pytest

from app.services.credential_vault import CredentialVault


@pytest.fixture(autouse=True)
def _clear_env_key(monkeypatch):
    monkeypatch.delenv("CREDENTIAL_MASTER_KEY", raising=False)


class TestCredentialVaultMasterKey:
    def test_dev_environment_allows_dev_fallback_key(self, monkeypatch):
        monkeypatch.setattr("app.config.get_settings", lambda: _settings("development"))
        vault = CredentialVault()
        assert vault._master_key.decode() == CredentialVault.DEV_FALLBACK_KEY

    def test_explicit_master_key_always_used(self, monkeypatch):
        monkeypatch.setenv("CREDENTIAL_MASTER_KEY", "per-install-secret-abcdefghijklmnopqrstuvwx")
        monkeypatch.setattr("app.config.get_settings", lambda: _settings("production"))
        vault = CredentialVault()
        assert vault._master_key.decode() == "per-install-secret-abcdefghijklmnopqrstuvwx"

    def test_production_requires_master_key(self, monkeypatch):
        monkeypatch.setattr("app.config.get_settings", lambda: _settings("production"))
        with pytest.raises(RuntimeError, match="CREDENTIAL_MASTER_KEY"):
            CredentialVault()

    def test_production_accepts_per_install_key(self, monkeypatch):
        monkeypatch.setenv("CREDENTIAL_MASTER_KEY", "per-install-secret-abcdefghijklmnopqrstuvwx")
        monkeypatch.setattr("app.config.get_settings", lambda: _settings("production"))
        vault = CredentialVault()
        encrypted = vault.encrypt_to_bytes({"shop_name": "demo"})
        assert vault.decrypt_from_bytes(encrypted)["shop_name"] == "demo"


def _settings(environment: str):
    from app.config import Settings

    return Settings(
        ENVIRONMENT=environment,
        SECRET_KEY="a" * 48,
        SENTRY_DSN="https://key@o.ingest.sentry.io/proj" if environment == "production" else "",
        DATABASE_APP_ROLE="nazmos_app" if environment == "production" else "",
    )


class TestConfigProductionValidators:
    def test_production_requires_database_app_role(self, monkeypatch):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="DATABASE_APP_ROLE"):
            _settings("production").__class__(
                ENVIRONMENT="production",
                SECRET_KEY="a" * 48,
                SENTRY_DSN="https://key@o.ingest.sentry.io/proj",
                DATABASE_APP_ROLE="",
            )

    def test_development_allows_empty_database_app_role(self):
        s = _settings("development")
        assert s.DATABASE_APP_ROLE == ""
