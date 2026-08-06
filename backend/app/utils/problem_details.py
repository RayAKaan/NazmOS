"""RFC 7807 Problem Details helpers.

Provides a consistent error envelope for every API error response.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from starlette.responses import JSONResponse


PROBLEM_TYPE_URIS = {
    400: "https://api.nazm.ai/errors/bad-request",
    401: "https://api.nazm.ai/errors/unauthorized",
    403: "https://api.nazm.ai/errors/forbidden",
    404: "https://api.nazm.ai/errors/not-found",
    409: "https://api.nazm.ai/errors/conflict",
    422: "https://api.nazm.ai/errors/validation-error",
    429: "https://api.nazm.ai/errors/rate-limited",
    500: "https://api.nazm.ai/errors/internal-error",
}


def problem_response(
    status: int,
    title: str,
    detail: str,
    request: Request | None = None,
    instance: str | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build a JSON response conforming to RFC 7807.

    The response always includes:
      - type: stable URI identifying the problem class
      - title: short human-readable summary
      - status: HTTP status code
      - detail: human-readable explanation specific to this occurrence
      - instance: request path or explicit URI
      - trace_id: correlation id for logs/Sentry

    Additional members may be supplied via ``extra``.
    """
    trace_id = getattr(request.state, "request_id", None) if request else None
    if not trace_id:
        trace_id = str(uuid.uuid4())

    content: dict[str, Any] = {
        "type": PROBLEM_TYPE_URIS.get(status, "https://api.nazm.ai/errors/internal-error"),
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance or (request.url.path if request else "/"),
        "trace_id": trace_id,
    }
    if extra:
        # Avoid overwriting reserved keys.
        for key, value in extra.items():
            content.setdefault(key, value)

    return JSONResponse(status_code=status, content=content)
