"""API version header middleware.

Adds an ``X-NazmOS-API-Version`` response header to every request so clients
and proxies can detect the running API version without parsing OpenAPI docs.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

API_VERSION = "2.1.0-ksa"
API_VERSION_HEADER = "X-NazmOS-API-Version"


class APIVersionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers[API_VERSION_HEADER] = API_VERSION
        return response
