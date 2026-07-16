from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple
import asyncio


class RateLimiter(BaseHTTPMiddleware):
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.requests: Dict[str, list] = defaultdict(list)
        self.auth_calls = 20
        self.auth_period = 60
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        
        if path.startswith("/api/v1/auth"):
            limit = self.auth_calls
            period = self.auth_period
        else:
            limit = self.calls
            period = self.period
        
        if not self._check_rate_limit(client_ip, limit, period):
            raise HTTPException(status_code=429, detail="Too many requests")
        
        response = await call_next(request)
        return response
    
    def _check_rate_limit(self, key: str, limit: int, period: int) -> bool:
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=period)
        
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if req_time > window_start
        ]
        
        if len(self.requests[key]) >= limit:
            return False
        
        self.requests[key].append(now)
        return True
