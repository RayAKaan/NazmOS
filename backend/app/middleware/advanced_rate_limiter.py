import time
import hashlib
from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis
import json


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
        self.redis = redis.from_url(redis_url, decode_responses=True)
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
        """Get unique identifier for the client."""
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
        
        return identifier
    
    def check_rate_limit(
        self,
        identifier: str,
        endpoint_key: str = "default"
    ) -> Tuple[bool, Dict]:
        """
        Check if request is within rate limit using sliding window algorithm.
        
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
        
        pipe = self.redis.pipeline()
        
        pipe.zremrangebyscore(key, 0, window_start)
        
        pipe.zcard(key)
        
        pipe.execute()
        
        current_count = self.redis.zcard(key)
        
        remaining = max(0, limit - current_count - 1)
        reset_time = int(now + window)
        
        if current_count >= limit:
            ttl = self.redis.ttl(key)
            retry_after = max(1, ttl if ttl > 0 else window)
            
            return False, {
                "limit": limit,
                "remaining": 0,
                "reset": reset_time,
                "retry_after": retry_after
            }
        
        self.redis.zadd(key, {f"{now}:{hashlib.md5(str(now).encode()).hexdigest()[:8]}": now})
        self.redis.expire(key, window)
        
        return True, {
            "limit": limit,
            "remaining": remaining,
            "reset": reset_time
        }
    
    async def check_rate_limit_async(
        self,
        identifier: str,
        endpoint_key: str = "default"
    ) -> Tuple[bool, Dict]:
        """Async version of check_rate_limit."""
        return self.check_rate_limit(identifier, endpoint_key)
    
    def get_usage(self, identifier: str, endpoint_key: str = "default") -> int:
        """Get current usage count for an identifier."""
        config = self.limits.get(endpoint_key, self.limits["default"])
        window = config["window"]
        prefix = config["key_prefix"]
        
        key = f"{prefix}:{identifier}"
        now = time.time()
        window_start = now - window
        
        self.redis.zremrangebyscore(key, 0, window_start)
        
        return self.redis.zcard(key)
    
    def reset_limit(self, identifier: str, endpoint_key: str = "default") -> bool:
        """Reset rate limit for an identifier."""
        config = self.limits.get(endpoint_key, self.limits["default"])
        prefix = config["key_prefix"]
        
        key = f"{prefix}:{identifier}"
        self.redis.delete(key)
        
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
            return f"user:{hashlib.md5(token.encode()).hexdigest()[:16]}"
        return f"ip:{ip}"


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
            return JSONResponse(
                status_code=429,
                content={"error": True, "code": "RATE_LIMITED", "message": "Too many requests"},
                headers={"Retry-After": str(info.get("retry_after", 60))},
            )

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
    """
    import os
    from app.config import get_settings

    settings = get_settings()
    is_dev = settings.ENVIRONMENT == "development"

    redis_url = os.getenv("REDIS_URL")
    if redis_url and not is_dev:
        try:
            return RedisRateLimiter(redis_url=redis_url)
        except Exception:
            pass

    if is_dev:
        limiter = InMemoryRateLimiter(default_limit=10000, window_seconds=60)
        # Relaxed dev limits so E2E/smoke tests can poll status endpoints freely.
        for key in limiter.limits:
            limiter.limits[key]["limit"] *= 100
        return limiter

    return InMemoryRateLimiter()


rate_limiter = get_rate_limiter()
