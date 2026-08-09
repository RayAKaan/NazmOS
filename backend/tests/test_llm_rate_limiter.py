"""Tests for the per-provider LLM rate limiter.

Covers the sliding-window RPM/TPM budgets, date-keyed RPD budgets with
per-provider reset timezones (groq UTC, google US/Pacific), token estimation,
and the fail-open Redis behavior.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.llm_rate_limiter import (
    InMemoryLLMRateLimiter,
    RedisLLMRateLimiter,
    PROVIDER_LIMITS,
    LLMRateLimitExceeded,
    estimate_tokens,
    _provider_day,
    _next_midnight_ts,
)


class StubAsyncRedis:
    """In-memory stub mimicking the subset of redis.asyncio the limiter uses."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.zsets = {}
        self.strings = {}
        self.expirations = {}

    def _maybe_fail(self):
        if self.fail:
            raise ConnectionError("connection refused")

    async def zremrangebyscore(self, key, min, max):
        self._maybe_fail()
        if key in self.zsets:
            self.zsets[key] = [(m, s) for (m, s) in self.zsets[key] if s > max]
        return 0

    async def zcard(self, key):
        self._maybe_fail()
        return len(self.zsets.get(key, []))

    async def zadd(self, key, mapping):
        self._maybe_fail()
        for m, s in mapping.items():
            self.zsets.setdefault(key, []).append((m, float(s)))

    async def zrangebyscore(self, key, min, max, withscores=False):
        self._maybe_fail()
        rows = [(m, s) for (m, s) in self.zsets.get(key, []) if s >= min and (max == "+inf" or s <= max)]
        if withscores:
            return [(m, s) for (m, s) in rows]
        return [m for (m, s) in rows]

    async def expire(self, key, seconds):
        self._maybe_fail()
        self.expirations[key] = seconds

    async def expireat(self, key, ts):
        self._maybe_fail()
        self.expirations[key] = ts

    async def get(self, key):
        self._maybe_fail()
        return self.strings.get(key)

    async def incrby(self, key, amount):
        self._maybe_fail()
        self.strings[key] = int(self.strings.get(key, 0)) + amount
        return self.strings[key]


def _redis_limiter(stub: StubAsyncRedis) -> RedisLLMRateLimiter:
    limiter = RedisLLMRateLimiter()
    limiter.redis = stub
    return limiter


async def test_redis_under_limit_records_request():
    stub = StubAsyncRedis()
    limiter = _redis_limiter(stub)

    await limiter.consume("groq", prompt_tokens=100, output_tokens=1000)

    assert len(stub.zsets["llm:rpm:groq"]) == 1
    assert stub.strings["llm:rpd:groq:" + _provider_day(PROVIDER_LIMITS, "groq")] == 1


async def test_redis_rpm_cap_raises():
    stub = StubAsyncRedis()
    limiter = _redis_limiter(stub)
    stub.zsets["llm:rpm:groq"] = [(f"m{i}", time.time()) for i in range(PROVIDER_LIMITS["groq"]["rpm"])]

    with pytest.raises(LLMRateLimitExceeded) as exc_info:
        await limiter.consume("groq")
    assert exc_info.value.budget == "rpm"


async def test_redis_rpd_cap_raises():
    stub = StubAsyncRedis()
    limiter = _redis_limiter(stub)
    day = _provider_day(PROVIDER_LIMITS, "groq")
    stub.strings[f"llm:rpd:groq:{day}"] = PROVIDER_LIMITS["groq"]["rpd"]

    with pytest.raises(LLMRateLimitExceeded) as exc_info:
        await limiter.consume("groq")
    assert exc_info.value.budget == "rpd"


async def test_redis_tpm_cap_raises():
    stub = StubAsyncRedis()
    limiter = _redis_limiter(stub)

    with pytest.raises(LLMRateLimitExceeded) as exc_info:
        await limiter.consume("groq", prompt_tokens=6000, output_tokens=1000)
    assert exc_info.value.budget == "tpm"


async def test_redis_outage_fails_open():
    stub = StubAsyncRedis(fail=True)
    limiter = _redis_limiter(stub)

    # A Redis outage must never block an LLM call — consume() fails open.
    await limiter.consume("groq")


async def test_redis_usage_reports_remaining():
    stub = StubAsyncRedis()
    limiter = _redis_limiter(stub)
    day = _provider_day(PROVIDER_LIMITS, "groq")
    stub.strings[f"llm:rpd:groq:{day}"] = 3

    usage = await limiter.usage()

    assert usage["groq"]["rpm_remaining"] == PROVIDER_LIMITS["groq"]["rpm"]
    assert usage["groq"]["rpd_used"] == 3
    assert usage["groq"]["rpd_remaining"] == PROVIDER_LIMITS["groq"]["rpd"] - 3
    assert usage["groq"]["rpd_reset_tz"] == "UTC"


async def test_in_memory_under_limit():
    limiter = InMemoryLLMRateLimiter()
    await limiter.consume("google", prompt_tokens=10, output_tokens=100)
    usage = await limiter.usage()
    assert usage["google"]["rpm_used"] == 1


async def test_in_memory_rpm_cap_raises():
    limiter = InMemoryLLMRateLimiter()
    for _ in range(PROVIDER_LIMITS["groq"]["rpm"]):
        await limiter.consume("groq")

    with pytest.raises(LLMRateLimitExceeded) as exc_info:
        await limiter.consume("groq")
    assert exc_info.value.budget == "rpm"


async def test_in_memory_rpd_cap_raises():
    limits = {"groq": {**PROVIDER_LIMITS["groq"], "rpd": 2, "rpm": 1000}}
    limiter = InMemoryLLMRateLimiter(limits)
    await limiter.consume("groq")
    await limiter.consume("groq")

    with pytest.raises(LLMRateLimitExceeded) as exc_info:
        await limiter.consume("groq")
    assert exc_info.value.budget == "rpd"


def test_provider_day_respects_provider_timezone():
    # 2026-08-08 01:00 UTC is still Aug 7 in US/Pacific (UTC-8).
    instant = datetime(2026, 8, 8, 1, 0, 0, tzinfo=ZoneInfo("UTC"))

    assert _provider_day(PROVIDER_LIMITS, "groq", instant) == "2026-08-08"
    assert _provider_day(PROVIDER_LIMITS, "google", instant) == "2026-08-07"


def test_next_midnight_is_in_provider_future():
    for provider in ("groq", "google"):
        ts = _next_midnight_ts(PROVIDER_LIMITS, provider)
        assert ts > time.time()
        assert ts - time.time() < 26 * 3600


def test_estimate_tokens():
    assert estimate_tokens("a" * 100) == 25
    assert estimate_tokens(None) == 1
    assert estimate_tokens("") == 1
