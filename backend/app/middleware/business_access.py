from uuid import UUID
from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user


async def assert_business_access(db: AsyncSession, business_id: str | UUID, current_user: User) -> None:
    """Verify that the current user owns or is an active team member of a business."""
    result = await db.execute(
        text("SELECT owner_id FROM businesses WHERE id = :id"),
        {"id": str(business_id)},
    )
    biz = result.fetchone()
    if not biz:
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

    raise HTTPException(403, "Not authorized for this business")


async def verify_business_access(
    business_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """FastAPI dependency for query/path based business_id access checks."""
    await assert_business_access(db, business_id, current_user)
    return business_id
