"""Partner program API – accountants, Monshaat advisors, fintechs."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_platform_operator
from app.services.partner_service import (
    register_partner,
    get_partner_by_user,
    get_partner_dashboard,
    record_referral,
    update_referral_status,
    list_active_partners,
    approve_partner,
)

router = APIRouter(prefix="/api/v1/partners", tags=["Partners"])


class PartnerApplyRequest(BaseModel):
    partner_type: str = Field(..., pattern=r"^(accountant|advisor|consultant|auditor|fintech)$")
    name: str = Field(..., min_length=2, max_length=255)
    email: str = Field(..., max_length=255)
    phone: str | None = Field(None, max_length=20)
    city: str | None = Field(None, max_length=100)
    cr_number: str | None = Field(None, max_length=20)
    monshaat_certified: bool = False
    commission_pct: float = Field(10.0, ge=0, le=50)
    bank_iban: str | None = Field(None, max_length=50)


class ReferralRequest(BaseModel):
    merchant_name: str = Field(..., min_length=1, max_length=255)
    merchant_email: str | None = Field(None, max_length=255)
    merchant_phone: str | None = Field(None, max_length=20)
    estimated_arr_sar: float | None = Field(None, ge=0)
    business_id: UUID | None = None
    notes: str | None = None


class ReferralStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(lead|converted|churned)$")
    payout_sar: float | None = Field(None, ge=0)


@router.post("/apply")
async def apply_partner(
    req: PartnerApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        partner = await register_partner(
            db,
            owner_user_id=current_user.id,
            partner_type=req.partner_type,
            name=req.name,
            email=req.email,
            phone=req.phone,
            city=req.city,
            cr_number=req.cr_number,
            monshaat_certified=req.monshaat_certified,
            commission_pct=req.commission_pct,
            bank_iban=req.bank_iban,
        )
        return {"ok": True, "partner": partner}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/me")
async def partner_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    partner = await get_partner_by_user(db, current_user.id)
    if not partner:
        raise HTTPException(404, "No partner application found")
    return {"partner": partner}


@router.get("/dashboard")
async def partner_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    partner = await get_partner_by_user(db, current_user.id)
    if not partner:
        raise HTTPException(404, "No partner application found")
    return await get_partner_dashboard(db, partner["id"])


@router.post("/referrals")
async def create_referral(
    req: ReferralRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    partner = await get_partner_by_user(db, current_user.id)
    if not partner:
        raise HTTPException(403, "Only active partners can record referrals")
    try:
        referral = await record_referral(
            db,
            partner_id=partner["id"],
            merchant_name=req.merchant_name,
            merchant_email=req.merchant_email,
            merchant_phone=req.merchant_phone,
            estimated_arr_sar=req.estimated_arr_sar,
            business_id=req.business_id,
            notes=req.notes,
        )
        return {"ok": True, "referral": referral}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/referrals/{referral_id}/status")
async def patch_referral_status(
    referral_id: UUID,
    req: ReferralStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    partner = await get_partner_by_user(db, current_user.id)
    if not partner:
        raise HTTPException(403, "Only active partners can update referrals")
    try:
        referral = await update_referral_status(
            db,
            partner_id=partner["id"],
            referral_id=referral_id,
            status=req.status,
            payout_sar=req.payout_sar,
        )
        return {"ok": True, "referral": referral}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/public")
async def public_partners(
    city: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    return {"partners": await list_active_partners(db, city=city, limit=limit)}


@router.post("/admin/{partner_id}/approve")
async def admin_approve_partner(
    partner_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Gated by the platform-operator identity (the owner) rather than the
    # non-existent "admin" role.
    await assert_platform_operator(db, current_user)
    try:
        partner = await approve_partner(db, partner_id, current_user.id)
        return {"ok": True, "partner": partner}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
