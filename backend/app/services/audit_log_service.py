"""Append-only audit log service.

Every security-relevant, data-governance, or money-affecting action should be
recorded via this service so founders and compliance officers can reconstruct
"who did what, when".
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog
from app.utils.logging_context import get_request_id

logger = logging.getLogger(__name__)


async def record(
    session: AsyncSession,
    action_type: str,
    action_category: str,
    business_id: UUID | str | None = None,
    organization_id: UUID | str | None = None,
    user_id: UUID | str | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | str | None = None,
    entity_name: str | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Record an audit event."""
    entry = AuditLog(
        business_id=business_id,
        organization_id=organization_id,
        user_id=user_id,
        user_email=user_email,
        user_role=user_role,
        action_type=action_type,
        action_category=action_category,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        old_value=old_value or {},
        new_value=new_value or {},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=get_request_id(),
        extra_metadata=extra_metadata or {},
    )
    session.add(entry)
    await session.commit()
    return entry


async def record_access_denial(
    *,
    business_id: UUID | str | None,
    user_id: UUID | str | None,
    user_email: str | None,
    user_role: str | None,
    capability: str,
    reason: str,
    path: str | None = None,
    ip_address: str | None = None,
) -> bool:
    """Best-effort write of a denied-access event to the AuditLog.

    Uses a dedicated session whose RLS tenant is explicitly scoped to the
    subject ``business_id``, so the denial is recorded even when the caller's
    own RLS tenant differs (cross-tenant attempts). Never raises: a failed
    audit write must not turn a clean 403 into a 500.
    """
    from app.database.connection import AsyncSessionLocal, _rls_tenant_id, set_rls_tenant_id

    token = set_rls_tenant_id(str(business_id) if business_id else None)
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                AuditLog(
                    business_id=business_id,
                    user_id=user_id,
                    user_email=user_email,
                    user_role=user_role,
                    action_type=f"access_denied_{capability}",
                    action_category="authorization",
                    entity_type="api",
                    entity_name=path,
                    new_value={
                        "reason": reason,
                        "capability": capability,
                        "path": path,
                        "attempted_business_id": str(business_id) if business_id else None,
                    },
                    ip_address=ip_address,
                    request_id=get_request_id(),
                    extra_metadata={},
                )
            )
            await session.commit()
        return True
    except Exception:
        logger.warning("access_denial_audit_write_failed", exc_info=True)
        return False
    finally:
        _rls_tenant_id.reset(token)
