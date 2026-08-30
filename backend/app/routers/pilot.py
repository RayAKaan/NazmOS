"""Phase 5 controlled pilot endpoints."""
from __future__ import annotations
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.services.ai_gateway import budget_snapshot
from app.services.pilot_mode import POLICY
from app.services.decision_explanation import build_explanation
from app.services.pilot_readiness import create_or_refresh_baseline, pilot_summary, daily_brief

router=APIRouter(prefix="/api/v1/pilot", tags=["Pilot"])

@router.get("/status")
async def status():
    return {"pilot_mode": POLICY.enabled, "require_approval": POLICY.require_approval,
            "real_execution": POLICY.allow_real_execution, "ai_enabled": POLICY.ai_enabled,
            "ai_budget": budget_snapshot()}

@router.get("/recommendations")
async def recommendations(business_id: UUID, db: AsyncSession=Depends(get_db), current_user: User=Depends(get_current_user)):
    await assert_business_access(db,business_id,current_user)
    result=await db.execute(text("""SELECT id, action_type, priority, title, description, expected_recovery_sar_v2,
        recoverable_value_low_sar, recoverable_value_high_sar, recovery_confidence, status, item_id, evidence
        FROM money_audit_actions WHERE business_id=:bid ORDER BY priority ASC, created_at DESC LIMIT 100"""),{"bid":str(business_id)})
    rows=[]
    for r in result.mappings():
        rows.append({"id":str(r["id"]),"action_type":r["action_type"],"priority":r["priority"],"title":r["title"],
                     "description":r["description"],"expected_recovery_sar":float(r["expected_recovery_sar_v2"] or 0),
                     "recoverable_value_low_sar":float(r["recoverable_value_low_sar"] or 0),
                     "recoverable_value_high_sar":float(r["recoverable_value_high_sar"] or 0),
                     "recovery_confidence":r["recovery_confidence"],"status":r["status"],"item_id":str(r["item_id"]) if r["item_id"] else None,
                     "execution_mode":"APPROVAL_REQUIRED" if POLICY.require_approval else "MANUAL"})
    return {"business_id":str(business_id),"count":len(rows),"recommendations":rows,"pilot_mode":True}

@router.post("/explain/{action_id}")
async def explain(action_id: UUID, business_id: UUID, db: AsyncSession=Depends(get_db), current_user: User=Depends(get_current_user)):
    await assert_business_access(db,business_id,current_user)
    r=(await db.execute(text("SELECT action_type,title,description,evidence FROM money_audit_actions WHERE id=:id AND business_id=:bid"),{"id":str(action_id),"bid":str(business_id)})).mappings().first()
    if not r: raise HTTPException(404,"Recommendation not found")
    evidence=r["evidence"] if isinstance(r["evidence"],dict) else {}
    return build_explanation(decision=str(r["action_type"] or "MANUAL_REVIEW").upper(), evidence=evidence, ai_reasoning=None)


@router.post("/baseline")
async def create_baseline(business_id: UUID, db: AsyncSession=Depends(get_db), current_user: User=Depends(get_current_user)):
    await assert_business_access(db, business_id, current_user)
    row = await create_or_refresh_baseline(db, business_id, owner_id=current_user.id)
    await db.commit()
    return {"id": str(row.id), "business_id": str(business_id), "snapshot": row.snapshot, "created_at": row.created_at, "updated_at": row.updated_at}

@router.get("/summary")
async def summary(business_id: UUID, db: AsyncSession=Depends(get_db), current_user: User=Depends(get_current_user)):
    await assert_business_access(db, business_id, current_user)
    return await pilot_summary(db, business_id)

@router.get("/daily-brief")
async def get_daily_brief(business_id: UUID, db: AsyncSession=Depends(get_db), current_user: User=Depends(get_current_user)):
    await assert_business_access(db, business_id, current_user)
    return await daily_brief(db, business_id)
