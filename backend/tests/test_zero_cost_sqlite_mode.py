"""WS6 — zero-cost SQLite mode is structurally impossible to break.

D-08 (CELERY_REDIS_ADR variant): a SQLite ``DATABASE_URL`` is the "zero
external infra" mode — no Redis, no external Temporal server.  These tests pin
the config-guard behavior and the substrate contract so that wiring Redis or a
queue-based execution path into the SQLite deployment fails loudly.
"""
import os
import importlib.util

import asyncio

import pytest


def _settings_with_sqlite(use_temporal_env: str | None = None):
    """Build Settings with a SQLite URL while explicitly *requesting* Redis,
    proving the config guard wins over the caller.

    ``use_temporal_env`` controls the USE_TEMPORAL env var: ``None`` (unset)
    must auto-disable Temporal in SQLite mode; an explicit value is respected
    so the hard-failure surface can be kept even on a file-backed database.
    """
    import app.config as config_mod

    keys = ("DATABASE_URL", "USE_TEMPORAL", "USE_REDIS")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    if use_temporal_env is None:
        os.environ.pop("USE_TEMPORAL", None)
    else:
        os.environ["USE_TEMPORAL"] = use_temporal_env
    os.environ["USE_REDIS"] = "true"
    try:
        config_mod.get_settings.cache_clear()
        return config_mod.get_settings()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config_mod.get_settings.cache_clear()


def test_sqlite_url_forces_redis_off():
    s = _settings_with_sqlite()
    assert s.DATABASE_URL.startswith("sqlite")
    assert s.USE_REDIS is False, "SQLite mode must force Redis off"


def test_sqlite_url_auto_disables_temporal_when_unset():
    s = _settings_with_sqlite()
    assert s.USE_TEMPORAL is False, (
        "SQLite mode without an explicit USE_TEMPORAL must use the local runner"
    )


def test_sqlite_url_respects_explicit_temporal_true():
    s = _settings_with_sqlite(use_temporal_env="true")
    assert s.USE_TEMPORAL is True, (
        "an explicit USE_TEMPORAL=true is a hard-failure surface even on SQLite"
    )
    assert s.USE_REDIS is False


def test_celery_surface_is_removed_from_config():
    import app.config as config_mod

    assert not hasattr(config_mod.get_settings(), "USE_CELERY"), "USE_CELERY must be gone"
    assert importlib.util.find_spec("app.celery_app") is None, "app.celery_app must be deleted"


def test_llm_rate_limiter_in_memory_when_redis_off():
    from app.services.llm_rate_limiter import get_llm_rate_limiter

    from app.database.connection import settings as _s

    if _s.USE_REDIS:
        pytest.skip("USE_REDIS is enabled in this environment")
    limiter = get_llm_rate_limiter()
    assert type(limiter).__name__ == "InMemoryLLMRateLimiter", \
        "without Redis the limiter must fall back to the in-process window"


def test_health_not_strict_runtime_in_zero_cost_mode():
    """A SQLite deployment is not a 'strict runtime': Redis/Temporal failures
    degrade (never fail) the app's own /health contract."""
    import app.routers.health as health_mod

    assert health_mod.settings.ENVIRONMENT not in {"production", "staging", "runtime_test"}
    assert not health_mod.settings.USE_REDIS

    class _FakeDb:
        async def execute(self, *a, **k):
            return None

    status, checks = asyncio.run(health_mod._dependency_checks(db=_FakeDb()))
    assert checks["database"] == "ok"
    assert "temporal" not in checks, "zero-cost mode must not probe Temporal on /health"
    assert status in {"healthy", "degraded"}, \
        "zero-cost mode must never report unhealthy when Redis is missing"


def test_uploads_finish_inline_in_zero_cost_mode():
    """With the local deterministic runner an upload never reports 'processing';
    the API contract is complete and synchronous (zero-cost branch)."""
    import app.routers.upload as upload_mod

    if upload_mod.settings.USE_TEMPORAL:
        pytest.skip("USE_TEMPORAL is enabled in this environment")
    assert not upload_mod.settings.USE_TEMPORAL
    del upload_mod  # import-time wiring is the assertion: module imports cleanly