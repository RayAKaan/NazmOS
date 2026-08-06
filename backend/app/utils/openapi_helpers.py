"""OpenAPI helpers for consistent response documentation and deprecation headers.

Every public router should include ``COMMON_ERROR_RESPONSES`` so generated
clients and contract tests see the same 400/401/403/422/429/500 shapes.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    type: str = Field(default="about:blank", description="RFC 7807 error type URI")
    title: str = Field(description="Short, human-readable summary")
    status: int = Field(description="HTTP status code")
    detail: str = Field(description="Detailed explanation of the error")
    instance: str | None = Field(default=None, description="Request path that caused the error")
    trace_id: str | None = Field(default=None, description="Sentry/OpenTelemetry trace ID if available")


COMMON_ERROR_RESPONSES = {
    400: {"model": ProblemDetail, "description": "Bad Request"},
    401: {"model": ProblemDetail, "description": "Unauthorized"},
    403: {"model": ProblemDetail, "description": "Forbidden"},
    422: {"model": ProblemDetail, "description": "Validation Error"},
    429: {"model": ProblemDetail, "description": "Rate Limited"},
    500: {"model": ProblemDetail, "description": "Internal Server Error"},
}
