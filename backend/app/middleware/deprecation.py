"""Middleware that adds RFC 8594 ``Sunset`` headers to deprecated endpoints.

Routers mark an endpoint for deprecation by setting ``openapi_extra``:

    @router.get("/legacy", openapi_extra={"sunset": "2026-12-31"})
    async def legacy_endpoint(): ...
"""
from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class DeprecationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        route = request.scope.get("route")
        if route is None:
            return response

        openapi_extra = getattr(route, "openapi_extra", None) or {}
        sunset = openapi_extra.get("sunset")
        if sunset:
            response.headers["Sunset"] = str(sunset)
            # Also expose the deprecation date to JavaScript clients.
            response.headers["Deprecation"] = f"sunset-date={sunset}"

        return response
