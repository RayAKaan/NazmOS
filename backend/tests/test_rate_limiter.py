"""Tests for the hardened rate limiter (Phase 1.4).

Covers: async Redis sliding-window behavior, fail-open/fail-closed handling on
Redis outage, tenant scoping, and the production fallback in get_rate_limiter.
"""
import logging
from unittest.mock import patch

import pytest
from fastapi import Request

from app.middleware.advanced_rate_limiter import (
    RedisRateLimiter,
    InMemoryRateLimiter,
    RateLimiterUnavailable,
    get_rate_limiter,
)


class StubAsyncRedis:
    """In-memory stub that mimics the subset of redis.asyncio used."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.zsets = {}
        self.expirations = {}

    def pipeline(self):
        return StubPipeline(self)

    async def zcard(self, key):
        self._maybe_fail()
        return len(self.zsets.get(key, []))

    async def zadd(self, key, mapping):
        self._maybe_fail()
        self.zsets.setdefault(key, []).append(list(mapping.keys())[0])

    async def expire(self, key, seconds):
        self._maybe_fail()
        self.expirations[key] = seconds

    async def ttl(self, key):
        self._maybe_fail()
        return self.expirations.get(key, -1)

    async def delete(self, key):
        self._maybe_fail()
        self.zsets.pop(key, None)
        return 1

    def _maybe_fail(self):
        if self.fail:
            raise ConnectionError("connection refused")


class StubPipeline:
    def __init__(self, redis):
        self.redis = redis
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def zremrangebyscore(self, key, min, max):
        self.commands.append(("zremrangebyscore", key))
        return self

    def zcard(self, key):
        self.commands.append(("zcard", key))
        return self

    async def execute(self):
        self.redis._maybe_fail()
        results = []
        for cmd, key in self.commands:
            if cmd == "zcard":
                results.append(len(self.redis.zsets.get(key, [])))
            else:
                results.append(0)
        self.commands = []
        return results


def _request(
    path: str,
    query: str = "",
    headers: dict[str, str] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "query_string": query.encode(),
        "client": ("1.2.3.4", 1234),
        "scheme": "http",
        "server": ("test", 80),
        "app": None,
        "route": None,
    }
    return Request(scope)


def _limiter_with(stub) -> RedisRateLimiter:
    limiter = RedisRateLimiter()
    limiter.redis = stub
    return limiter


async def test_allowed_below_limit():
    stub = StubAsyncRedis()
    limiter = _limiter_with(stub)

    allowed, info = await limiter.check_rate_limit_async("ip:1.2.3.4")

    assert allowed is True
    assert info["remaining"] == 299


async def test_limited_returns_429_info():
    stub = StubAsyncRedis()
    limiter = _limiter_with(stub)
    # Push past the default 300 limit by seeding the zset directly.
    stub.zsets["rate:ip:1.2.3.4"] = [f"ts{i}" for i in range(300)]

    allowed, info = await limiter.check_rate_limit_async("ip:1.2.3.4")

    assert allowed is False
    assert info["remaining"] == 0
    assert info["retry_after"] >= 1


async def test_redis_outage_raises_rate_limiter_unavailable():
    stub = StubAsyncRedis(fail=True)
    limiter = _limiter_with(stub)

    with pytest.raises(RateLimiterUnavailable):
        await limiter.check_rate_limit_async("ip:1.2.3.4", "default")


async def test_identifier_scopes_by_business_query():
    stub = StubAsyncRedis()
    limiter = _limiter_with(stub)

    req = _request("/api/v1/x", query="business_id=biz-1")
    assert limiter.get_client_identifier(req).endswith(":biz:biz-1")


async def test_identifier_scopes_by_business_header():
    stub = StubAsyncRedis()
    limiter = _limiter_with(stub)

    req = _request("/api/v1/x", headers={"X-Business-ID": "biz-9"})
    assert limiter.get_client_identifier(req).endswith(":biz:biz-9")


async def test_identifier_uses_ip_when_no_business():
    stub = StubAsyncRedis()
    limiter = _limiter_with(stub)

    req = _request("/api/v1/x")
    assert limiter.get_client_identifier(req) == "ip:1.2.3.4"


async def test_dev_fallback_returns_in_memory():
    settings = _settings(environment="development")
    with patch("app.config.get_settings", return_value=settings):
        limiter = get_rate_limiter()
    assert isinstance(limiter, InMemoryRateLimiter)


async def test_prod_no_redis_returns_fail_open_redis():
    settings = _settings(environment="production")
    with patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=True):
        with patch("app.config.get_settings", return_value=settings):
            limiter = get_rate_limiter()
    assert isinstance(limiter, RedisRateLimiter)


def _settings(environment: str):
    from app.config import Settings

    return Settings(
        ENVIRONMENT=environment,
        SECRET_KEY="x" * 48,
        SENTRY_DSN="https://fake@sentry.example/1",
        CORS_ORIGINS="https://app.example.com",
        REDIS_URL="redis://localhost:6379/0",
        DATABASE_APP_ROLE="nazmos_app" if environment == "production" else "",
        USE_MOCK_LLM=False if environment == "production" else True,
        CREDENTIAL_MASTER_KEY=("y" * 48) if environment == "production" else "",
    )
