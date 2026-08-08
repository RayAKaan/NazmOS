from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Business, User, get_db
from app.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/api/v1/businesses", tags=["Businesses"])


class BusinessBootstrapRequest(BaseModel):
    name: str = Field(default="My Store", min_length=1, max_length=255)
    type: str = Field(default="baqala", pattern="^(supermart|cafe|retail|hotel|restaurant|pharmacy|grocery|baqala)$")
    city: Optional[str] = "Riyadh"
    address: Optional[str] = None
    contact_phone: Optional[str] = None


def _business_row(row) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "type": row.type,
        "city": row.city,
        "address": row.address,
        "currency": row.currency,
        "timezone": row.timezone,
        "is_demo": bool(row.is_demo),
        "contact_phone": row.contact_phone,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/current")
async def current_business(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(text("""
        SELECT b.*
        FROM businesses b
        LEFT JOIN team_members tm ON tm.business_id = b.id AND tm.user_id = :uid AND tm.is_active = true
        WHERE b.is_active = true AND (b.owner_id = :uid OR tm.user_id IS NOT NULL)
        ORDER BY b.created_at ASC
        LIMIT 1
    """), {"uid": str(current_user.id)})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "No business found for this user")
    return _business_row(row)


@router.post("/bootstrap")
async def bootstrap_business(
    payload: BusinessBootstrapRequest = BusinessBootstrapRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create the user's first store if none exists, otherwise return it.

    This makes founder-led pilots and first login usable without manual DB seeding.
    """
    existing = await db.execute(text("""
        SELECT b.*
        FROM businesses b
        LEFT JOIN team_members tm ON tm.business_id = b.id AND tm.user_id = :uid AND tm.is_active = true
        WHERE b.is_active = true AND (b.owner_id = :uid OR tm.user_id IS NOT NULL)
        ORDER BY b.created_at ASC
        LIMIT 1
    """), {"uid": str(current_user.id)})
    row = existing.fetchone()
    if row:
        return _business_row(row)

    business = Business(
        name=payload.name,
        type=payload.type,
        address=payload.address,
        city=payload.city,
        owner_id=current_user.id,
        currency="SAR",
        timezone="Asia/Riyadh",
        contact_phone=payload.contact_phone,
        is_demo=False,
    )
    db.add(business)
    await db.commit()
    await db.refresh(business)
    return _business_row(business)
