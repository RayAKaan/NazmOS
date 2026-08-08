"""Idempotency-Key middleware for safe retries.

Stores successful JSON responses for mutating requests so that replaying the
same ``Idempotency-Key`` header on the same method/path returns the cached
response instead of re-executing the operation.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Set

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, StreamingResponse
from sqlalchemy import text

from app.database.connection import async_session_scope, get_rls_tenant_id
from app.database.models import IdempotencyKey

logger = logging.getLogger(__name__)

MUTATING_METHODS: Set[str] = {"POST", "PATCH", "PUT"}
IDEMPOTENCY_HEADER = "Idempotency-Key"
CACHE_TTL_HOURS = 24

# Sentinel for requests with no tenant (e.g. auth) so the unique scope still
# holds and tenant A can never replay tenant B's cached response.
NO_TENANT = "00000000-0000-0000-0000-000000000000"


def _business_scope(request: Request) -> str:
    """Resolve the current tenant for the idempotency cache scope."""
    return get_rls_tenant_id() or NO_TENANT


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
        method = request.method.upper()

        # Only consider mutating requests that carry an idempotency key.
        if not idempotency_key or method not in MUTATING_METHODS:
            return await call_next(request)

        scope_path = request.url.path
        cache_scope = f"{method}:{scope_path}"
        business_id = _business_scope(request)

        # 1. Check for an existing, non-expired cached response.
        cached = await self._lookup_cache(idempotency_key, method, scope_path, business_id)
        if cached is not None:
            logger.debug(
                "idempotency_cache_hit",
                key=idempotency_key,
                scope=cache_scope,
                status=cached["response_status"],
            )
            return Response(
                content=cached["response_body"].encode("utf-8"),
                status_code=cached["response_status"],
                headers={"Idempotency-Key-Replay": "true"},
                media_type="application/json",
            )

        # 2. Process the request and capture the response body.
        response = await call_next(request)

        # Do not cache streaming or non-JSON responses.
        if isinstance(response, StreamingResponse):
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        status_code = response.status_code
        if status_code < 200 or status_code >= 300:
            return response

        body = await self._read_response_body(response)
        if body is None:
            return response

        # 3. Store the response for future retries.
        try:
            await self._store_cache(
                idempotency_key=idempotency_key,
                method=method,
                scope_path=scope_path,
                business_id=business_id,
                request=request,
                response_status=status_code,
                response_body=body.decode("utf-8"),
            )
            response.headers["Idempotency-Key-Stored"] = "true"
        except Exception as exc:
            # Caching failures must not fail the original request.
            logger.warning("idempotency_cache_store_failed", error=str(exc))

        return response

    async def _lookup_cache(self, key: str, method: str, path: str, business_id: str):
        try:
            async with async_session_scope() as db:
                result = await db.execute(
                    text("""
                        SELECT response_status, response_body
                        FROM idempotency_keys
                        WHERE business_id = :business_id
                          AND idempotency_key = :key
                          AND scope_method = :method
                          AND scope_path = :path
                          AND expires_at > NOW()
                    """),
                    {"business_id": business_id, "key": key, "method": method, "path": path},
                )
                row = result.fetchone()
                if row:
                    return {
                        "response_status": row.response_status,
                        "response_body": row.response_body,
                    }
        except Exception as exc:
            logger.warning("idempotency_cache_lookup_failed", error=str(exc))
        return None

    async def _store_cache(
        self,
        *,
        idempotency_key: str,
        method: str,
        scope_path: str,
        business_id: str,
        request: Request,
        response_status: int,
        response_body: str,
    ) -> None:
        request_hash = await self._request_hash(request)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS)

        async with async_session_scope() as db:
            await db.execute(
                text("""
                    INSERT INTO idempotency_keys
                        (id, business_id, idempotency_key, scope_method, scope_path,
                         request_hash, response_status, response_body, expires_at, created_at)
                    VALUES
                        (gen_random_uuid(), :business_id, :key, :method, :path,
                         :request_hash, :response_status, :response_body, :expires_at, NOW())
                    ON CONFLICT (business_id, idempotency_key, scope_method, scope_path)
                    DO UPDATE SET
                        request_hash = EXCLUDED.request_hash,
                        response_status = EXCLUDED.response_status,
                        response_body = EXCLUDED.response_body,
                        expires_at = EXCLUDED.expires_at
                """),
                {
                    "business_id": business_id,
                    "key": idempotency_key,
                    "method": method,
                    "path": scope_path,
                    "request_hash": request_hash,
                    "response_status": response_status,
                    "response_body": response_body,
                    "expires_at": expires_at,
                },
            )
            await db.commit()

    async def _request_hash(self, request: Request) -> str | None:
        """Best-effort hash of the request body for change detection."""
        try:
            body = await request.body()
            if body:
                return hashlib.sha256(body).hexdigest()
        except Exception:
            pass
        return None

    async def _read_response_body(self, response: Response) -> bytes | None:
        try:
            if hasattr(response, "body") and response.body is not None:
                return response.body
        except Exception:
            pass
        return None
