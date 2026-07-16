"""
NazmOS Recovery Match API.

Manual-confirm retailer-to-retailer stock recovery. This is not a public marketplace,
not escrow, not delivery, and not payment processing.
"""
from uuid import UUID
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.middleware.feature_gate import require_feature
from app.services.recovery_match_service import (
    get_or_create_settings,
    update_settings,
    generate_preview,
    create_listing,
    suggest_matches_for_listing,
    buyer_mark_interested,
    reveal_contact,
    complete_match,
    reject_match,
    report_match_issue,
)

router = APIRouter(prefix="/api/v1/recovery-match", tags=["Recovery Match"])


class RecoveryMatchSettingsUpdate(BaseModel):
    business_id: UUID
    is_enabled: Optional[bool] = None
    allow_contact_reveal: Optional[bool] = None
    max_distance_km: Optional[float] = Field(None, ge=1, le=50)
    allowed_categories: Optional[List[str]] = None
    excluded_categories: Optional[List[str]] = None


class CreateListingRequest(BaseModel):
    business_id: UUID
    item_id: UUID
    quantity_available: float = Field(..., gt=0)
    asking_price_sar: Optional[float] = Field(None, ge=0)
    discount_pct: float = Field(20, ge=0, le=90)
    expiry_date: str = Field(..., description="YYYY-MM-DD. Required for real matches.")
    batch_number: Optional[str] = None
    seller_branch_id: Optional[UUID] = None
    listing_days: int = Field(7, ge=1, le=30)
    notes: Optional[str] = None


class MatchActionRequest(BaseModel):
    business_id: UUID
    recovered_value_sar: Optional[float] = None
    notes: Optional[str] = None


class ReportIssueRequest(BaseModel):
    business_id: UUID
    issue_type: str = Field(..., examples=["wrong_quantity", "wrong_condition", "near_expiry", "no_show", "other"])
    notes: Optional[str] = None


@router.get("/settings")
async def get_settings(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    return await get_or_create_settings(db, business_id)


@router.put("/settings")
async def put_settings(
    req: RecoveryMatchSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, req.business_id, current_user)
    await require_feature(db, req.business_id, "recovery_match", required_plan="Growing Retail")
    return await update_settings(db, req.business_id, req.model_dump(exclude={"business_id"}, exclude_none=True))


@router.get("/preview")
async def get_recovery_match_preview(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    await require_feature(db, business_id, "recovery_match_preview", required_plan="Free Money Audit")
    opportunities = await generate_preview(db, business_id)
    return {
        "business_id": str(business_id),
        "mode": "preview",
        "title": "Recovery Match Preview",
        "description": "Healthy surplus stock that may become recoverable through nearby retailer matching once your plan and local network density allow it.",
        "guardrails": [
            "No medicine, baby formula, cold-chain, expired, or near-expiry goods in v1.",
            "No payments, escrow, delivery, or invoice generation in v1.",
            "Both seller and buyer must manually confirm before contact reveal.",
        ],
        "opportunities": opportunities,
        "count": len(opportunities),
    }


@router.post("/listings")
async def create_recovery_listing(
    req: CreateListingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, req.business_id, current_user)
    await require_feature(db, req.business_id, "recovery_match", required_plan="Growing Retail")
    try:
        listing = await create_listing(db, req.business_id, req.model_dump(exclude={"business_id"}))
        return {"ok": True, "listing": listing}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/listings")
async def list_recovery_listings(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    await require_feature(db, business_id, "recovery_match", required_plan="Growing Retail")
    res = await db.execute(text("""
        SELECT * FROM stock_recovery_listings
        WHERE seller_business_id = :business_id
        ORDER BY created_at DESC
        LIMIT 100
    """), {"business_id": str(business_id)})
    return {"listings": [dict(r._mapping) for r in res.fetchall()]}


@router.post("/listings/{listing_id}/suggest-matches")
async def suggest_matches(
    listing_id: UUID,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    await require_feature(db, business_id, "recovery_match", required_plan="Growing Retail")
    try:
        matches = await suggest_matches_for_listing(db, listing_id, business_id)
        return {"ok": True, "matches": matches, "count": len(matches)}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/matches")
async def list_matches(
    business_id: UUID = Query(...),
    role: str = Query("buyer", pattern="^(buyer|seller)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    await require_feature(db, business_id, "recovery_match", required_plan="Growing Retail")
    if role == "seller":
        query = """
            SELECT m.*, l.item_name, l.sku, l.asking_price_sar, l.quantity_available
            FROM stock_recovery_matches m
            JOIN stock_recovery_listings l ON l.id = m.listing_id
            WHERE l.seller_business_id = :business_id
            ORDER BY m.created_at DESC
            LIMIT 100
        """
    else:
        query = """
            SELECT m.*, l.item_name, l.sku, l.asking_price_sar, l.quantity_available
            FROM stock_recovery_matches m
            JOIN stock_recovery_listings l ON l.id = m.listing_id
            WHERE m.buyer_business_id = :business_id
            ORDER BY m.created_at DESC
            LIMIT 100
        """
    res = await db.execute(text(query), {"business_id": str(business_id)})
    return {"matches": [dict(r._mapping) for r in res.fetchall()]}


@router.post("/matches/{match_id}/buyer-interest")
async def mark_buyer_interest(
    match_id: UUID,
    req: MatchActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, req.business_id, current_user)
    await require_feature(db, req.business_id, "recovery_match", required_plan="Growing Retail")
    try:
        match = await buyer_mark_interested(db, match_id, req.business_id)
        return {"ok": True, "match": match}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/matches/{match_id}/reveal-contact")
async def reveal_match_contact(
    match_id: UUID,
    req: MatchActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, req.business_id, current_user)
    await require_feature(db, req.business_id, "recovery_match_contact_reveal", required_plan="Growing Retail")
    try:
        return await reveal_contact(db, match_id, req.business_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/matches/{match_id}/complete")
async def complete_recovery_match(
    match_id: UUID,
    req: MatchActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, req.business_id, current_user)
    await require_feature(db, req.business_id, "recovery_match", required_plan="Growing Retail")
    if req.recovered_value_sar is None:
        raise HTTPException(422, "recovered_value_sar is required")
    try:
        match = await complete_match(db, match_id, req.business_id, req.recovered_value_sar)
        return {"ok": True, "match": match}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/matches/{match_id}/reject")
async def reject_recovery_match(
    match_id: UUID,
    req: MatchActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, req.business_id, current_user)
    await require_feature(db, req.business_id, "recovery_match", required_plan="Growing Retail")
    try:
        return await reject_match(db, match_id, req.business_id, req.notes)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/matches/{match_id}/report-issue")
async def report_recovery_match_issue(
    match_id: UUID,
    req: ReportIssueRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, req.business_id, current_user)
    await require_feature(db, req.business_id, "recovery_match", required_plan="Growing Retail")
    try:
        return await report_match_issue(db, match_id, req.business_id, req.issue_type, req.notes)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/status")
async def recovery_match_status(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, business_id, current_user)
    try:
        await require_feature(db, business_id, "recovery_match", required_plan="Growing Retail")
        enabled = True
    except Exception:
        enabled = False
    return {
        "business_id": str(business_id),
        "recovery_match_enabled": enabled,
        "phase": "manual-confirm pilot",
        "message": "Recovery Match is being built as a manual-first retailer-to-retailer stock recovery network.",
    }
