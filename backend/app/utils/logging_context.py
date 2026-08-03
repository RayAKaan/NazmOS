"""Request-scoped logging context.

Real production systems attach a correlation/request ID to every log line so that
incidents can be traced across middleware, services, and background workers. This
module provides a simple contextvar-based implementation that is safe for async
code and does not require a full distributed-tracing backend.
"""
from __future__ import annotations

import contextvars
import uuid
from typing import Optional

request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
business_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "business_id", default=None
)


def set_request_id(request_id: Optional[str]) -> None:
    request_id_ctx.set(request_id)


def get_request_id() -> Optional[str]:
    return request_id_ctx.get()


def set_business_id(business_id: Optional[str]) -> None:
    business_id_ctx.set(business_id)


def get_business_id() -> Optional[str]:
    return business_id_ctx.get()


def generate_request_id() -> str:
    return str(uuid.uuid4())
