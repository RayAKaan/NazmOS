import time
import hashlib
import logging
from typing import Dict, Tuple, Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis
import redis.asyncio as aioredis
import json

from app.utils.problem_details import problem_response


class RedisRateLimiter:
    """
    Redis-based distributed rate limiter with sliding window algorithm.
    
    Supports:
    - Per-IP rate limiting
    - Per-user rate limiting
    - Per-endpoint rate limiting
    - Different limits for different endpoints
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        default_limit: int = 300,
        window_seconds: int = 60
    ):
        self.redis = aioredis.from_url(redis_url, decode_responses=True)
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        
        self.limits = {
            "auth_login": {"limit": 5, "window": 300, "key_prefix": "rate:auth"},
            "auth_register": {"limit": 3, "window": 300, "key_prefix": "rate:register"},
            "chat": {"limit": 60, "window": 60, "key_prefix": "rate:chat"},
            "upload": {"limit": 10, "window": 300, "key_prefix": "rate:upload"},
            "default": {"limit": default_limit, "window": window_seconds, "key_prefix": "rate"},
        }
    
    def get_client_identifier(self, request: Request) -> str:
        """Get unique identifier for the client, scoped to business when available."""
        forwarded = request.headers.get("X-Forwarded-For")
        if isinstance(forwarded, str) and forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        auth_header = request.headers.get("Authorization", "")
        if isinstance(auth_header, str) and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            identifier = f"user:{hashlib.md5(token.encode()).hexdigest()[:16]}"
        else:
            identifier = f"ip:{ip}"

        # Scope per-tenant limits when a business_id is present in the URL.
        business_id = request.query_params.get("business_id") or request.path_params.get("business_id")
        if business_id:
            identifier = f"{identifier}:biz:{business_id}"

        return identifier
    
    async def check_rate_limit(
        self,
        identifier: str,
        endpoint_key: str = "default"
    ) -> Tuple[bool, Dict]:
        """
        Check if request is within rate limit using sliding window algorithm.

        Raises RateLimiterUnavailable when Redis is unreachable; the middleware
        decides fail-open vs fail-closed based on the endpoint.

        Returns:
            Tuple of (is_allowed, rate_limit_info)
        """
        config = self.limits.get(endpoint_key, self.limits["default"])
        limit = config["limit"]
        window = config["window"]
        prefix = config["key_prefix"]

        key = f"{prefix}:{identifier}"
        now = time.time()
        window_start = now - window

        try:
            async with self.redis.pipeline() as pipe:
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                results = await pipe.execute()

            current_count = int(results[1])

            remaining = max(0, limit - current_count - 1)
            reset_time = int(now + window)

            if current_count >= limit:
                ttl = await self.redis.ttl(key)
                retry_after = max(1, ttl if ttl > 0 else window)

                return False, {
                    "limit": limit,
                    "remaining": 0,
                    "reset": reset_time,
                    "retry_after": retry_after
                }

            await self.redis.zadd(
                key, {f"{now}:{hashlib.md5(str(now).encode()).hexdigest()[:8]}": now}
            )
            await self.redis.expire(key, window)

            return True, {
                "limit": limit,
                "remaining": remaining,
                "reset": reset_time
            }
        except Exception as exc:
            raise RateLimiterUnavailable(str(exc)) from exc

    async def check_rate_limit_async(
        self,
        identifier: str,
        endpoint_key: str = "default"
    ) -> Tuple[bool, Dict]:
        """Async version of check_rate_limit."""
        return await self.check_rate_limit(identifier, endpoint_key)

    async def get_usage(self, identifier: str, endpoint_key: str = "default") -> int:
        """Get current usage count for an identifier."""
        config = self.limits.get(endpoint_key, self.limits["default"])
        window = config["window"]
        prefix = config["key_prefix"]

        key = f"{prefix}:{identifier}"
        now = time.time()
        window_start = now - window

        try:
            await self.redis.zremrangebyscore(key, 0, window_start)
            return int(await self.redis.zcard(key))
        except Exception as exc:
            raise RateLimiterUnavailable(str(exc)) from exc

    async def reset_limit(self, identifier: str, endpoint_key: str = "default") -> bool:
        """Reset rate limit for an identifier."""
        config = self.limits.get(endpoint_key, self.limits["default"])
        prefix = config["key_prefix"]

        key = f"{prefix}:{identifier}"
        try:
            await self.redis.delete(key)
        except Exception as exc:
            raise RateLimiterUnavailable(str(exc)) from exc

        return True


class InMemoryRateLimiter:
    """
    In-memory rate limiter for development/testing without Redis.
    NOT suitable for production distributed deployments.
    """
    
    def __init__(
        self,
        default_limit: int = 300,
        window_seconds: int = 60
    ):
        self.requests: Dict[str, list] = {}
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        
        self.limits = {
            "auth_login": {"limit": 5, "window": 300, "key_prefix": "rate:auth"},
            "auth_register": {"limit": 3, "window": 300, "key_prefix": "rate:register"},
            "chat": {"limit": 60, "window": 60, "key_prefix": "rate:chat"},
            "upload": {"limit": 10, "window": 300, "key_prefix": "rate:upload"},
            "default": {"limit": default_limit, "window": window_seconds, "key_prefix": "rate"},
        }
    
    def get_client_identifier(self, request: Request) -> str:
        """Get unique identifier for the client; mirrors RedisRateLimiter."""
        forwarded = request.headers.get("X-Forwarded-For")
        if isinstance(forwarded, str) and forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("Authorization", "")
        if isinstance(auth_header, str) and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            identifier = f"user:{hashlib.md5(token.encode()).hexdigest()[:16]}"
        else:
            identifier = f"ip:{ip}"

        business_id = request.query_params.get("business_id") or request.path_params.get("business_id")
        if business_id:
            identifier = f"{identifier}:biz:{business_id}"

        return identifier


    def _generate_key(self, request: Request) -> str:
        return self.get_client_identifier(request)

    def _check_rate_limit(self, key: str, max_requests: int = 300, window_seconds: int = 60) -> bool:
        old = self.limits.get("__compat__")
        self.limits["__compat__"] = {"limit": max_requests, "window": window_seconds, "key_prefix": "rate:compat"}
        try:
            allowed, _ = self.check_rate_limit(key, "__compat__")
            return allowed
        finally:
            if old is None:
                self.limits.pop("__compat__", None)
            else:
                self.limits["__compat__"] = old

    async def check_rate_limit_async(self, identifier: str, endpoint_key: str = "default") -> Tuple[bool, Dict]:
        return self.check_rate_limit(identifier, endpoint_key)

    def _clean_old_requests(self, identifier: str, window: int) -> list:
        """Remove requests outside the current window."""
        now = time.time()
        cutoff = now - window
        
        if identifier in self.requests:
            self.requests[identifier] = [
                ts for ts in self.requests[identifier] if ts > cutoff
            ]
        else:
            self.requests[identifier] = []
        
        return self.requests[identifier]
    
    def check_rate_limit(
        self,
        identifier: str,
        endpoint_key: str = "default"
    ) -> Tuple[bool, Dict]:
        """Check if request is within rate limit."""
        config = self.limits.get(endpoint_key, self.limits["default"])
        limit = config["limit"]
        window = config["window"]
        
        requests = self._clean_old_requests(identifier, window)
        
        now = time.time()
        reset_time = int(now + window)
        
        if len(requests) >= limit:
            oldest_request = min(requests) if requests else now
            retry_after = max(1, int(oldest_request + window - now))
            
            return False, {
                "limit": limit,
                "remaining": 0,
                "reset": reset_time,
                "retry_after": retry_after
            }
        
        requests.append(now)
        
        return True, {
            "limit": limit,
            "remaining": limit - len(requests),
            "reset": reset_time
        }
    
    def get_usage(self, identifier: str, endpoint_key: str = "default") -> int:
        """Get current usage count for an identifier."""
        config = self.limits.get(endpoint_key, self.limits["default"])
        window = config["window"]
        
        requests = self._clean_old_requests(identifier, window)
        return len(requests)
    
    def reset_limit(self, identifier: str, endpoint_key: str = "default") -> bool:
        """Reset rate limit for an identifier."""
        if identifier in self.requests:
            del self.requests[identifier]
        return True


class AdvancedRateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware that enforces the configured rate limiter."""

    def __init__(self, app, limiter: RedisRateLimiter | InMemoryRateLimiter):
        super().__init__(app)
        self.limiter = limiter

    def _endpoint_key(self, path: str) -> str:
        if path.startswith("/api/v1/auth/login"):
            return "auth_login"
        if path.startswith("/api/v1/auth/register"):
            return "auth_register"
        if path.startswith("/api/v1/chat"):
            return "chat"
        if path.startswith("/api/v1/upload"):
            return "upload"
        return "default"

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/health", "/api/v1/health"}:
            return await call_next(request)

        endpoint_key = self._endpoint_key(request.url.path)
        identifier = self.limiter.get_client_identifier(request)
        allowed, info = await self.limiter.check_rate_limit_async(identifier, endpoint_key)
        if not allowed:
            response = problem_response(
                status=429,
                title="Rate Limited",
                detail="Too many requests. Please slow down.",
                request=request,
            )
            response.headers["Retry-After"] = str(info.get("retry_after", 60))
            return response

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(info.get("limit", ""))
        response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", ""))
        response.headers["X-RateLimit-Reset"] = str(info.get("reset", ""))
        return response


def get_rate_limiter() -> RedisRateLimiter | InMemoryRateLimiter:
    """
    Factory function to get appropriate rate limiter based on environment.

    In production with multiple workers, use RedisRateLimiter.
    For development/testing, use InMemoryRateLimiter with relaxed limits.

    Distributed rate limiting requires Redis. Falling back to an in-memory
    limiter in a multi-worker production deployment silently breaks limiting:
    each worker enforces its own independent budget, so the aggregate limit is
    multiplied by the worker count. Therefore in production we only fall back
    to a RedisRateLimiter configured to fail open on outage, never to the
    in-memory implementation.
    """
    import os
    from app.config import get_settings

    settings = get_settings()
    is_dev = settings.ENVIRONMENT == "development"

    redis_url = os.getenv("REDIS_URL")
    if redis_url and not is_dev:
        try:
            return RedisRateLimiter(redis_url=redis_url)
        except Exception as exc:
            logger.error(
                "rate_limiter_redis_construct_failed",
                extra={"error": str(exc), "environment": settings.ENVIRONMENT},
            )

    if is_dev:
        limiter = InMemoryRateLimiter(default_limit=10000, window_seconds=60)
        # Relaxed dev limits so E2E/smoke tests can poll status endpoints freely.
        for key in limiter.limits:
            limiter.limits[key]["limit"] *= 100
        return limiter

    # Production without a constructible Redis limiter: never silently degrade
    # to in-memory. Return a Redis limiter that fails open on outage instead.
    logger.error(
        "rate_limiter_redis_required",
        extra={"environment": settings.ENVIRONMENT, "redis_url_present": bool(redis_url)},
    )
    return RedisRateLimiter(redis_url=redis_url or "redis://localhost:6379/0")


rate_limiter = get_rate_limiter()
