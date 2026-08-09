from uuid import UUID
from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.services.audit_log_service import record_access_denial
from app.services.capabilities_service import is_platform_operator


async def _log_denial(
    db: AsyncSession,
    *,
    business_id: str | UUID | None,
    current_user: User,
    capability: str,
    reason: str,
) -> None:
    await record_access_denial(
        business_id=business_id,
        user_id=current_user.id,
        user_email=current_user.email,
        user_role=current_user.role,
        capability=capability,
        reason=reason,
    )


async def assert_business_access(db: AsyncSession, business_id: str | UUID, current_user: User) -> None:
    """Verify that the current user owns or is an active team member of a business."""
    result = await db.execute(
        text("SELECT owner_id FROM businesses WHERE id = :id"),
        {"id": str(business_id)},
    )
    biz = result.fetchone()
    if not biz:
        await _log_denial(
            db, business_id=business_id, current_user=current_user,
            capability="tenant_access", reason="business_not_found",
        )
        raise HTTPException(404, "Business not found")

    if str(biz.owner_id) == str(current_user.id):
        return

    tm = await db.execute(text("""
        SELECT 1
        FROM team_members
        WHERE business_id = :bid
          AND user_id = :uid
          AND is_active = true
        LIMIT 1
    """), {"bid": str(business_id), "uid": str(current_user.id)})
    if tm.fetchone():
        return

    await _log_denial(
        db, business_id=business_id, current_user=current_user,
        capability="tenant_access", reason="not_owner_or_team_member",
    )
    raise HTTPException(403, "Not authorized for this business")


async def assert_platform_operator(
    db: AsyncSession,
    current_user: User,
    business_id: str | UUID | None = None,
) -> None:
    """Require the NazmOS platform operator identity (founder).

    Used to gate the ops console and platform admin tools. Denials are
    recorded to the AuditLog and surfaced as 403.
    """
    if not is_platform_operator(current_user):
        await _log_denial(
            db, business_id=business_id, current_user=current_user,
            capability="is_platform_operator",
            reason="not_platform_operator",
        )
        raise HTTPException(403, "Platform operator access required")



async def verify_business_access(
    business_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """FastAPI dependency for query/path based business_id access checks."""
    await assert_business_access(db, business_id, current_user)
    return business_id
