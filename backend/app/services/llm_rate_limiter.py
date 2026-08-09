"""Per-provider LLM rate limiter for the real Groq + Google Gemini providers.

Limits are ORG-WIDE (global) per provider, independent of business_id, so a
multi-tenant deployment shares one budget exactly as the free tiers bill it:

    groq   : 30 RPM / 6,000 TPM / 14,400 RPD  (resets midnight UTC)
    google : 15 RPM / 1,000 RPD               (resets midnight US/Pacific)

RPM/TPM use a sliding 60s window (Redis zset); RPD uses a date-keyed counter
that resets at midnight in the provider's own timezone.

The orchestrator runs a pre-flight ``consume()`` before every provider call and
skips to the next provider when ``LLMRateLimitExceeded`` is raised. When every
real provider is exhausted the chat layer returns an honest capacity message —
it never silently degrades to the mock provider.
"""
from __future__ import annotations

import math
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger("llm_rate_limiter")

PROVIDER_LIMITS: dict[str, dict[str, Any]] = {
    "groq": {
        "rpm": 30,
        "tpm": 6000,
        "rpd": 14400,
        "rpd_tz": "UTC",
    },
    "google": {
        "rpm": 15,
        "tpm": None,
        "rpd": 1000,
        "rpd_tz": "US/Pacific",
    },
}

RPM_WINDOW_SECONDS = 60.0


class LLMRateLimitExceeded(Exception):
    """Raised when a provider budget (rpm/tpm/rpd) would be exceeded."""

    def __init__(self, provider: str, budget: str, limit: int, current: int):
        self.provider = provider
        self.budget = budget
        self.limit = limit
        self.current = current
        super().__init__(
            f"llm_rate_limited:{provider}:{budget} (used {current}/{limit})"
        )


def estimate_tokens(text: str | None) -> int:
    """Rough token estimate (~4 chars/token) with a safety margin."""
    return max(1, math.ceil(len(text or "") / 4))


def _provider_tz(limits: dict[str, Any], provider: str) -> ZoneInfo:
    tz_name = limits[provider].get("rpd_tz", "UTC")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _provider_day(
    limits: dict[str, Any], provider: str, now: datetime | None = None
) -> str:
    return (now or datetime.now(_provider_tz(limits, provider))).astimezone(
        _provider_tz(limits, provider)
    ).date().isoformat()


def _next_midnight_ts(limits: dict[str, Any], provider: str) -> int:
    tz = _provider_tz(limits, provider)
    now = datetime.now(tz)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(next_midnight.timestamp())


class InMemoryLLMRateLimiter:
    """In-memory fallback for development/tests. Not for multi-worker production."""

    def __init__(self, limits: dict[str, dict[str, Any]] | None = None):
        self.limits = limits or PROVIDER_LIMITS
        self.rpm: dict[str, list[float]] = {}
        self.tpm: dict[str, list[tuple[float, int]]] = {}
        self.rpd: dict[str, dict[str, int]] = {}

    async def consume(
        self,
        provider: str,
        prompt_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        cfg = self.limits.get(provider)
        if cfg is None:
            return
        now = time.time()
        window_start = now - RPM_WINDOW_SECONDS

        stamps = [ts for ts in self.rpm.get(provider, []) if ts > window_start]
        if len(stamps) >= cfg["rpm"]:
            raise LLMRateLimitExceeded(provider, "rpm", cfg["rpm"], len(stamps))

        tokens = [(ts, n) for ts, n in self.tpm.get(provider, []) if ts > window_start]
        if cfg.get("tpm"):
            used = sum(n for _, n in tokens)
            if used + prompt_tokens + output_tokens > cfg["tpm"]:
                raise LLMRateLimitExceeded(provider, "tpm", cfg["tpm"], used)

        day = _provider_day(self.limits, provider)
        used_daily = self.rpd.get(provider, {}).get(day, 0)
        if used_daily + 1 > cfg["rpd"]:
            raise LLMRateLimitExceeded(provider, "rpd", cfg["rpd"], used_daily)

        self.rpm[provider] = stamps + [now]
        if cfg.get("tpm"):
            self.tpm[provider] = tokens + [(now, prompt_tokens + output_tokens)]
        self.rpd.setdefault(provider, {})[day] = used_daily + 1

    async def usage(self) -> dict[str, dict[str, Any]]:
        now = time.time()
        out: dict[str, dict[str, Any]] = {}
        for provider, cfg in self.limits.items():
            rpm_used = len([ts for ts in self.rpm.get(provider, []) if ts > now - RPM_WINDOW_SECONDS])
            day = _provider_day(self.limits, provider)
            rpd_used = self.rpd.get(provider, {}).get(day, 0)
            out[provider] = {
                "provider": provider,
                "rpm_remaining": max(0, cfg["rpm"] - rpm_used),
                "rpm_used": rpm_used,
                "rpd_remaining": max(0, cfg["rpd"] - rpd_used),
                "rpd_used": rpd_used,
                "rpd_reset_tz": cfg.get("rpd_tz"),
            }
        return out


class RedisLLMRateLimiter:
    """Redis-backed distributed limiter (sliding window + date-keyed RPD)."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        limits: dict[str, dict[str, Any]] | None = None,
    ):
        self.redis = aioredis.from_url(redis_url, decode_responses=True)
        self.limits = limits or PROVIDER_LIMITS

    async def _sliding_count(self, key: str, window: float, now: float) -> int:
        await self.redis.zremrangebyscore(key, 0, now - window)
        return int(await self.redis.zcard(key))

    async def consume(
        self,
        provider: str,
        prompt_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        cfg = self.limits.get(provider)
        if cfg is None:
            return
        try:
            await self._consume_redis(provider, cfg, prompt_tokens, output_tokens)
        except LLMRateLimitExceeded:
            raise
        except Exception as exc:
            # Fail open: a Redis outage must never block merchant-facing LLM calls.
            logger.warning("llm_rate_limiter_redis_unavailable", extra={"provider": provider, "error": str(exc)})

    async def _consume_redis(
        self,
        provider: str,
        cfg: dict[str, Any],
        prompt_tokens: int,
        output_tokens: int,
    ) -> None:
        now = time.time()

        rpm_key = f"llm:rpm:{provider}"
        rpm_used = await self._sliding_count(rpm_key, RPM_WINDOW_SECONDS, now)
        if rpm_used >= cfg["rpm"]:
            raise LLMRateLimitExceeded(provider, "rpm", cfg["rpm"], rpm_used)

        tpm_used = 0
        if cfg.get("tpm"):
            tpm_key = f"llm:tpm:{provider}"
            await self.redis.zremrangebyscore(tpm_key, 0, now - RPM_WINDOW_SECONDS)
            rows = await self.redis.zrangebyscore(
                tpm_key, now - RPM_WINDOW_SECONDS, "+inf", withscores=True
            )
            tpm_used = int(sum(float(score) for _, score in rows))
            estimated = prompt_tokens + output_tokens
            if tpm_used + estimated > cfg["tpm"]:
                raise LLMRateLimitExceeded(provider, "tpm", cfg["tpm"], tpm_used)

        day = _provider_day(self.limits, provider)
        rpd_key = f"llm:rpd:{provider}:{day}"
        rpd_used = int(await self.redis.get(rpd_key) or 0)
        if rpd_used + 1 > cfg["rpd"]:
            raise LLMRateLimitExceeded(provider, "rpd", cfg["rpd"], rpd_used)

        await self.redis.zadd(rpm_key, {str(now): now})
        await self.redis.expire(rpm_key, int(RPM_WINDOW_SECONDS))
        if cfg.get("tpm"):
            await self.redis.zadd(tpm_key, {str(now): float(prompt_tokens + output_tokens)})
            await self.redis.expire(tpm_key, int(RPM_WINDOW_SECONDS))
        await self.redis.incrby(rpd_key, 1)
        await self.redis.expireat(rpd_key, _next_midnight_ts(self.limits, provider))

    async def usage(self) -> dict[str, dict[str, Any]]:
        now = time.time()
        out: dict[str, dict[str, Any]] = {}
        for provider, cfg in self.limits.items():
            rpm_used = await self._sliding_count(f"llm:rpm:{provider}", RPM_WINDOW_SECONDS, now)
            day = _provider_day(self.limits, provider)
            rpd_used = int(await self.redis.get(f"llm:rpd:{provider}:{day}") or 0)
            out[provider] = {
                "provider": provider,
                "rpm_remaining": max(0, cfg["rpm"] - rpm_used),
                "rpm_used": rpm_used,
                "rpd_remaining": max(0, cfg["rpd"] - rpd_used),
                "rpd_used": rpd_used,
                "rpd_reset_tz": cfg.get("rpd_tz"),
            }
        return out


def get_llm_rate_limiter():
    """Factory: Redis-backed when USE_REDIS, in-memory otherwise."""
    settings = get_settings()
    if settings.USE_REDIS:
        try:
            return RedisLLMRateLimiter(redis_url=settings.REDIS_URL)
        except Exception as exc:
            logger.warning("llm_rate_limiter_redis_construct_failed", extra={"error": str(exc)})
            return InMemoryLLMRateLimiter()
    return InMemoryLLMRateLimiter()


llm_rate_limiter = get_llm_rate_limiter()
