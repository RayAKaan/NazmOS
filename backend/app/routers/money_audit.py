from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import User, get_db
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.services.money_audit_service import (
    generate_money_audit,
    get_latest_money_audit,
    get_money_audit,
    printable_html,
    update_action_status,
    whatsapp_summary,
)

router = APIRouter(prefix="/api/v1/money-audit", tags=["Money Audit"])


class GenerateAuditRequest(BaseModel):
    business_id: UUID


class ActionStatusRequest(BaseModel):
    business_id: UUID
    notes: Optional[str] = None
    completed_value_sar: Optional[float] = Field(default=None, ge=0)
    approval_channel: str = "dashboard"


async def _audit_business_id(db: AsyncSession, audit_id: UUID | str) -> str:
    result = await db.execute(text("SELECT business_id FROM money_audits WHERE id = :id"), {"id": str(audit_id)})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Money Audit not found")
    return str(row.business_id)


@router.get("/current")
async def current_money_audit(
    business_id: UUID = Query(...),
    auto_generate: bool = Query(default=True, description="Generate first audit if no audit exists yet."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(business_id), current_user)
    audit = await get_latest_money_audit(db, business_id)
    if audit:
        return audit
    if not auto_generate:
        return {"audit": None, "message": "No Money Audit generated yet."}
    return await generate_money_audit(db, business_id, current_user.id)


@router.post("/generate")
async def generate_audit(
    payload: GenerateAuditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(payload.business_id), current_user)
    return await generate_money_audit(db, payload.business_id, current_user.id)


@router.get("/{audit_id}")
async def read_money_audit(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business_id = await _audit_business_id(db, audit_id)
    await assert_business_access(db, business_id, current_user)
    try:
        return await get_money_audit(db, audit_id)
    except ValueError:
        raise HTTPException(404, "Money Audit not found")


@router.get("/{audit_id}/whatsapp-summary", response_class=PlainTextResponse)
async def read_whatsapp_summary(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business_id = await _audit_business_id(db, audit_id)
    await assert_business_access(db, business_id, current_user)
    audit = await get_money_audit(db, audit_id)
    return whatsapp_summary(audit)


@router.get("/{audit_id}/print", response_class=HTMLResponse)
async def read_printable_report(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business_id = await _audit_business_id(db, audit_id)
    await assert_business_access(db, business_id, current_user)
    audit = await get_money_audit(db, audit_id)
    return HTMLResponse(printable_html(audit))


@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: UUID,
    payload: ActionStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(payload.business_id), current_user)
    try:
        return await update_action_status(
            db,
            action_id,
            payload.business_id,
            "approved",
            notes=payload.notes,
            approval_channel=payload.approval_channel,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/actions/{action_id}/reject")
async def reject_action(
    action_id: UUID,
    payload: ActionStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(payload.business_id), current_user)
    try:
        return await update_action_status(
            db,
            action_id,
            payload.business_id,
            "rejected",
            notes=payload.notes,
            approval_channel=payload.approval_channel,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/actions/{action_id}/complete")
async def complete_action(
    action_id: UUID,
    payload: ActionStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_business_access(db, str(payload.business_id), current_user)
    try:
        return await update_action_status(
            db,
            action_id,
            payload.business_id,
            "completed",
            notes=payload.notes,
            completed_value_sar=payload.completed_value_sar,
            approval_channel=payload.approval_channel,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))
