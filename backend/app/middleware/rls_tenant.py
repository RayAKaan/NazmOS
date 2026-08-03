"""Tenant context propagation for PostgreSQL Row-Level Security.

This middleware extracts a ``business_id`` from path parameters, query
parameters, or JSON form bodies and stores it in a context variable.  The
async database session helpers then issue ``SET LOCAL app.current_tenant_id``
so that RLS policies in PostgreSQL can enforce row-level isolation even if an
application query forgets a ``business_id`` filter.

In development (SQLite or when running as the Postgres table owner) the
policies may be bypassed, but the context is still set so the defence is active
as soon as a non-owner application role is used.
"""
from __future__ import annotations

import json
import logging
from contextvars import Token
from uuid import UUID

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.database.connection import (
    set_rls_tenant_id,
    clear_rls_tenant_id,
    get_rls_tenant_id,
    _rls_tenant_id,
)

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token: Token | None = None
        try:
            tenant_id = await self._extract_business_id(request)
            if tenant_id:
                token = set_rls_tenant_id(str(tenant_id))
                logger.debug("rls_tenant_set", path=request.url.path, tenant_id=str(tenant_id))
            response = await call_next(request)
            return response
        finally:
            if token is not None:
                try:
                    _rls_tenant_id.reset(token)
                except Exception:
                    clear_rls_tenant_id()

    async def _extract_business_id(self, request: Request) -> UUID | None:
        # 1. FastAPI path parameter (most reliable after routing).
        raw = request.path_params.get("business_id")
        if raw:
            return self._as_uuid(raw)

        # 2. Query string.
        raw = request.query_params.get("business_id")
        if raw:
            return self._as_uuid(raw)

        # 3. JSON body for mutating requests.  We intentionally do NOT parse
        # multipart/form-data here; doing so would consume the upload stream
        # before FastAPI/file endpoints can handle it efficiently.
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body_bytes = await request.body()
                    if body_bytes:
                        body = json.loads(body_bytes.decode("utf-8"))
                        if isinstance(body, dict):
                            raw = body.get("business_id")
                            if raw:
                                return self._as_uuid(raw)
                except Exception:
                    pass

        return None

    @staticmethod
    def _as_uuid(value) -> UUID | None:
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (ValueError, TypeError):
            return None
