"""Prometheus metrics exposure and request instrumentation.

Metrics are only emitted when ``PROMETHEUS_ENABLED=true``.  The middleware
records per-endpoint latency and response-code counters; the ``/metrics``
endpoint exposes them in Prometheus text format.
"""
from __future__ import annotations

import time

from fastapi import Request, Response
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

settings = get_settings()


class _NoMetrics:
    """No-op fallback used when Prometheus is disabled."""

    def observe(self, *args, **kwargs):
        pass

    def inc(self, *args, **kwargs):
        pass


if settings.PROMETHEUS_ENABLED:
    REQUEST_COUNT = Counter(
        "nazmos_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status_code"],
    )
    REQUEST_LATENCY = Histogram(
        "nazmos_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )
else:
    REQUEST_COUNT = _NoMetrics()
    REQUEST_LATENCY = _NoMetrics()


def _safe_label(value: str | int) -> str:
    """Make a Prometheus label value safe without losing readability."""
    return str(value).replace('"', '\\"')


def _normalized_path(request: Request) -> str:
    """Return the route template (e.g. ``/api/v1/items/{item_id}``) instead of
    the concrete URL so label cardinality stays bounded per route.

    Falls back to the raw path when routing has not matched a route (404s,
    early aborts) or the matched route exposes no template.
    """
    scope = request.scope
    # FastAPI >=0.135 wraps included routers in _IncludedRouter mounts whose
    # effective route context carries the fully-prefixed path template
    # (e.g. /api/v1/inventory/{item_id}/detail). Prefer it so labels stay
    # stable regardless of the include prefix.
    fastapi_scope = scope.get("fastapi") or {}
    effective_context = fastapi_scope.get("effective_route_context")
    template = getattr(effective_context, "path", None)
    if not template:
        route = scope.get("route")
        template = getattr(route, "path", None)
    if template:
        return template
    return scope.get("path", "/unknown")


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            if settings.PROMETHEUS_ENABLED:
                duration = time.perf_counter() - start
                path = _normalized_path(request)
                method = request.method
                REQUEST_LATENCY.labels(
                    method=_safe_label(method), path=_safe_label(path)
                ).observe(duration)
                REQUEST_COUNT.labels(
                    method=_safe_label(method),
                    path=_safe_label(path),
                    status_code=_safe_label(status_code),
                ).inc()


def metrics_response() -> Response:
    """Return the Prometheus metrics payload."""
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
