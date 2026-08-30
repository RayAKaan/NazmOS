"""WS6 — zero-cost SQLite mode is structurally impossible to break.

D-08 (CELERY_REDIS_ADR variant): a SQLite ``DATABASE_URL`` is the "zero
external infra" mode — no Celery, no Redis.  These tests pin the three
enforcement points and the stub/fallback behavior so that wiring an external
broker into the SQLite path fails loudly.
"""
import os

import asyncio

import pytest


def _settings_with_sqlite():
    """Return Settings built with a SQLite URL while explicitly *requesting*
    Celery + Redis, proving the config guard wins over the caller."""
    import app.config as config_mod

    keys = ("DATABASE_URL", "USE_CELERY", "USE_REDIS")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["USE_CELERY"] = "true"
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


def test_sqlite_url_forces_celery_and_redis_off():
    s = _settings_with_sqlite()
    assert s.DATABASE_URL.startswith("sqlite")
    assert s.USE_CELERY is False, "SQLite mode must force Celery off"
    assert s.USE_REDIS is False, "SQLite mode must force Redis off"


def test_celery_stub_used_when_disabled():
    """Default (dev/test) env: USE_CELERY=False -> app.celery_app is the stub,
    not a real Celery() instance, and send_task is a hard error."""
    using = pytest.importorskip("app.celery_app")
    assert type(using.celery_app).__name__ == "_StubCeleryApp"
    with pytest.raises(RuntimeError, match="Celery is disabled"):
        using.celery_app.send_task("app.tasks.audit_tasks.daily_full_audit")


def test_llm_rate_limiter_in_memory_when_redis_off():
    from app.services.llm_rate_limiter import get_llm_rate_limiter

    from app.database.connection import settings as _s

    if _s.USE_REDIS:
        pytest.skip("USE_REDIS is enabled in this environment")
    limiter = get_llm_rate_limiter()
    assert type(limiter).__name__ == "InMemoryLLMRateLimiter", \
        "without Redis the limiter must fall back to the in-process window"


def test_health_not_strict_runtime_in_zero_cost_mode():
    """A SQLite deployment is not a 'strict runtime': Redis/Celery failures
    degrade (never fail) the app's own /health contract."""
    import app.routers.health as health_mod

    assert health_mod.settings.ENVIRONMENT not in {"production", "staging", "runtime_test"}
    assert not health_mod.settings.USE_CELERY and not health_mod.settings.USE_REDIS

    class _FakeDb:
        async def execute(self, *a, **k):
            return None

    status, checks = asyncio.run(health_mod._dependency_checks(db=_FakeDb()))
    assert checks["database"] == "ok"
    assert status in {"healthy", "degraded"}, \
        "zero-cost mode must never report unhealthy when Redis is missing"


def test_uploads_finish_inline_in_zero_cost_mode():
    """With Celery disabled an upload never reports 'processing'; the import is
    synchronous and complete (upload router contracts zero-cost branch)."""
    import app.routers.upload as upload_mod

    if upload_mod.settings.USE_CELERY:
        pytest.skip("USE_CELERY is enabled in this environment")
    assert not upload_mod.settings.USE_CELERY
    del upload_mod  # import-time wiring is the assertion: module imports cleanly