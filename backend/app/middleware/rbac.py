"""
Role-Based Access Control (RBAC) Middleware for NazmOS KSA.

Provides FastAPI dependencies for role and permission checks.
Roles: owner > admin > manager > staff
"""
from functools import wraps
from typing import List, Optional, Callable
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user


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
