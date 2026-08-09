from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import User, get_db
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

    Atomic by construction: the unique partial index
    uq_businesses_active_owner (owner_id WHERE is_active = true) plus
    ON CONFLICT DO NOTHING means concurrent bootstraps can never create
    two stores for the same owner.
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

    business_id = str(uuid4())
    await db.execute(text("""
        INSERT INTO businesses
            (id, name, type, address, city, owner_id, currency, timezone, contact_phone, is_demo, is_active)
        VALUES
            (:id, :name, :type, :address, :city, :owner_id, 'SAR', 'Asia/Riyadh', :contact_phone, false, true)
        ON CONFLICT (owner_id) WHERE is_active = true DO NOTHING
    """), {
        "id": business_id,
        "name": payload.name,
        "type": payload.type,
        "address": payload.address,
        "city": payload.city,
        "owner_id": str(current_user.id),
        "contact_phone": payload.contact_phone,
    })
    await db.commit()

    result = await db.execute(text("""
        SELECT b.*
        FROM businesses b
        WHERE b.is_active = true AND b.owner_id = :uid
        ORDER BY b.created_at ASC
        LIMIT 1
    """), {"uid": str(current_user.id)})
    created = result.fetchone()
    if created is None:
        raise HTTPException(500, "Failed to bootstrap business")
    return _business_row(created)
