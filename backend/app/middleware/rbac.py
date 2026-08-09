"""
Role-Based Access Control (RBAC) Middleware for NazmOS KSA.

Provides FastAPI dependencies for role and permission checks.
Roles: owner > admin > manager > staff
"""
from functools import wraps
from typing import List, Optional, Callable
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.services.audit_log_service import record_access_denial
from app.services.capabilities_service import build_capabilities


ROLE_HIERARCHY = {
    "owner": 4,
    "admin": 3,
    "manager": 2,
    "staff": 1,
}

ROLE_PERMISSIONS = {
    "owner": [
        "read", "write", "delete", "manage_team", "manage_billing",
        "manage_settings", "view_reports", "manage_integrations",
        "manage_compliance", "export_data", "manage_roles",
    ],
    "admin": [
        "read", "write", "delete", "manage_team", "view_reports",
        "manage_integrations", "manage_compliance", "export_data",
    ],
    "manager": [
        "read", "write", "view_reports", "export_data",
    ],
    "staff": [
        "read",
    ],
}


def _role_level(role: str) -> int:
    return ROLE_HIERARCHY.get(role, 0)


def _has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, [])


def require_role(*allowed_roles: str):
    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_role = getattr(current_user, "role", "staff")
        if user_role not in allowed_roles and user_role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' is not authorized. Required: {', '.join(allowed_roles)}",
            )
        return current_user
    return dependency


def require_min_role(min_role: str):
    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_role = getattr(current_user, "role", "staff")
        if _role_level(user_role) < _role_level(min_role) and user_role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' does not meet minimum requirement of '{min_role}'",
            )
        return current_user
    return dependency


def require_permission(permission: str):
    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_role = getattr(current_user, "role", "staff")
        if not _has_permission(user_role, permission) and user_role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' lacks required permission: '{permission}'",
            )
        return current_user
    return dependency


def require_any_permission(*permissions: str):
    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_role = getattr(current_user, "role", "staff")
        if user_role == "owner":
            return current_user
        if not any(_has_permission(user_role, p) for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' lacks required permissions: {', '.join(permissions)}",
            )
        return current_user
    return dependency


def require_capability(capability: str, business_id: str | None = None):
    """Require a capability computed by ``capabilities_service``.

    This is the enforcement half of the capabilities model: the same object
    the frontend renders from is re-checked here on every request, so a UI
    decision is never the actual gate. ``business_id`` is the request parameter
    name (query or path) to read when the capability is business-scoped; when
    omitted, the capability is evaluated at platform level or against the
    request's validated tenant context.

    Denials are recorded to the AuditLog (action_category="authorization")
    and surfaced as 403.
    """
    async def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        biz = None
        if business_id:
            raw = request.query_params.get(business_id) or request.path_params.get(business_id)
            if raw:
                biz = str(raw)
        if biz is None and hasattr(request.state, "tenant_context"):
            tenant_context = request.state.tenant_context
            if tenant_context is not None and getattr(tenant_context, "business_id", None):
                biz = str(tenant_context.business_id)

        caps = await build_capabilities(db, current_user, biz)
        if not caps.has(capability):
            await record_access_denial(
                business_id=biz or (caps.business_id if caps.business_id else None),
                user_id=current_user.id,
                user_email=current_user.email,
                user_role=current_user.role,
                capability=capability,
                reason=f"missing capability: {capability}",
                path=request.url.path,
                ip_address=request.client.host if request.client else None,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing capability: {capability}",
            )
        return current_user
    return dependency
