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
            await self._set_tenant_context(request, tenant_id)
            response = await call_next(request)
            return response
        finally:
            if token is not None:
                try:
                    _rls_tenant_id.reset(token)
                except Exception:
                    clear_rls_tenant_id()

    async def _set_tenant_context(self, request: Request, raw_business_id: UUID | None) -> None:
        """Populate ``request.state.tenant_context`` from the authenticated user.

        The tenant-scoped routers (actions, adapters, organizations,
        subscriptions) read ``request.state.tenant_context`` via their
        ``get_current_tenant`` dependency. It was never assigned anywhere, so
        every route in those modules returned 401 even with a valid token.

        The context is always derived from the authenticated user's own
        accessible businesses (owned, team member, or organization-owned) and
        never from a client-supplied ``business_id`` alone, so it cannot be
        used to pivot into another tenant. On any auth/DB failure we simply
        leave the attribute unset so public routes keep working and the
        tenant-scoped routes return their existing 401.
        """
        authorization = request.headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            return
        try:
            raw_token = authorization.split(" ", 1)[1].strip()
        except IndexError:
            return
        if not raw_token:
            return

        from app.utils.security import verify_access_token
        from app.database.connection import AsyncSessionLocal
        from app.database.models import Business, User, TeamMember, Organization
        from app.services.multi_tenant import TenantContext, tenant_context as tenant_ctx_var
        from sqlalchemy import select

        valid, payload = verify_access_token(raw_token)
        if not valid or not payload:
            return
        user_id_raw = payload.get("sub")
        if not user_id_raw:
            return
        try:
            user_uuid = UUID(user_id_raw)
        except (ValueError, TypeError):
            return

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(User).where(User.id == user_uuid))
                user = result.scalar_one_or_none()
                if not user or not user.is_active:
                    return

                owned_ids = set(
                    (await session.execute(select(Business.id).where(Business.owner_id == user.id))).scalars().all()
                )
                team_ids = set(
                    (await session.execute(
                        select(TeamMember.business_id).where(
                            TeamMember.user_id == user.id,
                            TeamMember.is_active == True,
                        )
                    )).scalars().all()
                )
                org_ids = set(
                    (await session.execute(select(Organization.id).where(Organization.owner_id == user.id))).scalars().all()
                )
                org_business_ids = set()
                if org_ids:
                    org_business_ids = set(
                        (await session.execute(
                            select(Business.id).where(Business.organization_id.in_(org_ids))
                        )).scalars().all()
                    )

                candidates = sorted(owned_ids | team_ids | org_business_ids, key=str)
                if not candidates:
                    return

                # Prefer the request's explicit scope when the user may access
                # it; otherwise fall back to a deterministic default business.
                if raw_business_id is not None and UUID(str(raw_business_id)) in candidates:
                    business_id = UUID(str(raw_business_id))
                else:
                    business_id = candidates[0]

                business = await session.get(Business, business_id)
                context = TenantContext(
                    business_id=business_id,
                    organization_id=business.organization_id if business else None,
                    user_id=user.id,
                    user_role=user.role or "owner",
                    permissions=[],
                )
                request.state.tenant_context = context
                tenant_ctx_var.set(context)
        except Exception:
            logger.debug("tenant_context_resolve_failed", path=request.url.path, exc_info=True)

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
