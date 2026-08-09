"""
Nazm Agent API – KSA
Attention feed + approval queue + autonomy dial
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession
import json
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.services.agent_action_executor import approve_agent_action, reject_agent_action
from app.services.autonomy_service import execute_if_autonomous, dry_run_action
from app.services.feature_flags import require_feature_enabled
from app.services.intelligence_api_client import IntelligenceAPIClient

router = APIRouter(prefix="/api/v1/agent", tags=["Nazm Agent"])

R_RIYADH = timezone(timedelta(hours=3))

def _now():
    return datetime.now(R_RIYADH)


@router.get("/feed")
async def get_feed(
    business_id: UUID,
    status: str = "pending_approval,critical,info_only",
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attention feed – ranked by urgency – the owner's home screen"""
    await assert_business_access(db, business_id, current_user)
    await require_feature_enabled(db, "agent_enabled", business_id=business_id)
    allowed_statuses = {
        "pending_approval", "critical", "info_only", "approved",
        "rejected", "auto_executed", "executed", "failed",
    }
    statuses = [s.strip() for s in status.split(",") if s.strip() in allowed_statuses]
    if not statuses:
        statuses = ["pending_approval", "critical", "info_only"]

    query = text("""
        SELECT * FROM agent_actions
        WHERE business_id = :b
          AND status IN :statuses
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY 
          CASE status WHEN 'critical' THEN 0 WHEN 'pending_approval' THEN 1 ELSE 2 END,
          confidence DESC,
          created_at DESC
        LIMIT :lim
    """).bindparams(bindparam("statuses", expanding=True))
    result = await db.execute(query, {"b": str(business_id), "statuses": statuses, "lim": limit})
    
    rows = result.fetchall()
    items = []
    for r in rows:
        payload = r.payload if isinstance(r.payload, dict) else json.loads(r.payload or "{}")
        items.append({
            "id": str(r.id),
            "action_type": r.action_type,
            "status": r.status,
            "confidence": float(r.confidence),
            "priority": r.priority,
            "title": r.title,
            "title_ar": r.title_ar,
            "summary": r.summary,
            "summary_ar": r.summary_ar,
            "payload": payload,
            "estimated_value_sar": float(r.estimated_value_sar) if r.estimated_value_sar else None,
            "created_at": r.created_at.isoformat(),
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "can_approve": r.status == "pending_approval",
        })
    
    return {"items": items, "count": len(items), "has_more": len(items) == limit}


@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: UUID,
    business_id: UUID,
    note: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve – one tap – WhatsApp / Web"""
    # Verify ownership
    res = await db.execute(text(
        "SELECT a.*, b.owner_id FROM agent_actions a JOIN businesses b ON b.id = a.business_id WHERE a.id = :id"
    ), {"id": str(action_id)})
    row = res.fetchone()
    if not row:
        raise HTTPException(404, "Action not found")
    if str(row.business_id) != str(business_id):
        raise HTTPException(403, "Business mismatch")
    
    # Simple owner check
    if str(row.owner_id) != str(current_user.id):
        raise HTTPException(403, "Only the business owner can approve actions")

    await require_feature_enabled(db, "agent_enabled", business_id=business_id)

    result = await approve_agent_action(
        db,
        action_id,
        note=note or "Approved via NazmOS web dashboard",
        decided_by=current_user.id,
    )
    return {"ok": result.get("ok", False), "action_id": str(action_id), "status": "approved", "outcome": result.get("outcome")}


@router.post("/actions/{action_id}/reject")
async def reject_action(
    action_id: UUID,
    business_id: UUID,
    reason: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ownership = await db.execute(text(
        "SELECT a.id FROM agent_actions a JOIN businesses b ON b.id = a.business_id "
        "WHERE a.id = :id AND b.owner_id = :uid"
    ), {"id": str(action_id), "uid": str(current_user.id)})
    if not ownership.fetchone():
        raise HTTPException(404, "Action not found or access denied")

    await require_feature_enabled(db, "agent_enabled", business_id=business_id)

    result = await reject_agent_action(db, action_id, note=reason or "Rejected via NazmOS web dashboard")
    return {"ok": result.get("ok", False), "status": "rejected"}


# ── Autonomy Dial ─────────────────────────────────────

@router.get("/autonomy")
async def get_autonomy(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current autonomy dial settings – per action type"""
    await assert_business_access(db, business_id, current_user)
    # Default policies – KSA safe
    defaults = [
        {"action_type": "restock", "dial": 50, "label": "إعادة الطلب", "label_en": "Restocking", "ceiling_sar": 2000},
        {"action_type": "pricing_increase", "dial": 20, "label": "رفع الأسعار", "label_en": "Price Increase", "max_price_increase_pct": 5},
        {"action_type": "pricing_decrease", "dial": 30, "label": "خفض الأسعار", "label_en": "Price Decrease", "max_price_decrease_pct": 10},
        {"action_type": "cash_alert", "dial": 0, "label": "التدفق النقدي", "label_en": "Cash Flow", "ceiling_sar": 0},
        {"action_type": "staff_schedule", "dial": 0, "label": "جدولة الموظفين", "label_en": "Staffing", "ceiling_sar": 0},
        {"action_type": "expiry_alert", "dial": 50, "label": "تنبيهات انتهاء الصلاحية", "label_en": "Expiry Alerts", "ceiling_sar": 0},
    ]
    
    res = await db.execute(text(
        "SELECT action_type, dial, ceiling_sar, max_price_increase_pct, max_price_decrease_pct FROM autonomy_policies WHERE business_id = :b AND is_active = true"
    ), {"b": str(business_id)})
    
    saved = {r.action_type: r for r in res.fetchall()}
    
    policies = []
    for d in defaults:
        s = saved.get(d["action_type"])
        policies.append({
            "action_type": d["action_type"],
            "label": d["label"],
            "label_en": d["label_en"],
            "dial": s.dial if s else d["dial"],
            "ceiling_sar": float(s.ceiling_sar) if s and s.ceiling_sar else d.get("ceiling_sar"),
            "max_price_increase_pct": float(s.max_price_increase_pct) if s and s.max_price_increase_pct else d.get("max_price_increase_pct"),
            "max_price_decrease_pct": float(s.max_price_decrease_pct) if s and s.max_price_decrease_pct else d.get("max_price_decrease_pct"),
            "description_ar": "0 = أخبرني فقط / 50 = جهز وانتظر موافقتي / 100 = نفذ تلقائيا",
            "description_en": "0 = inform only / 50 = draft + approve / 100 = auto-execute",
        })
    
    return {"policies": policies}


class AutonomyPolicyIn(BaseModel):
    action_type: str
    dial: int = Field(default=50, ge=0, le=100)
    ceiling_sar: float | None = None
    max_price_increase_pct: float | None = None
    max_price_decrease_pct: float | None = None


class SetAutonomyRequest(BaseModel):
    policies: list[AutonomyPolicyIn]


@router.put("/autonomy")
async def set_autonomy(
    business_id: UUID,
    body: SetAutonomyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update autonomy dial – 0-100 per action_type"""
    await assert_business_access(db, business_id, current_user)
    for p in body.policies:
        action_type = p.action_type
        dial = max(0, min(100, int(p.dial)))
        
        # Enforce safety ceilings – pricing never >50 without explicit override
        if action_type.startswith("pricing") and dial > 50:
            dial = 50
        
        await db.execute(text("""
            INSERT INTO autonomy_policies 
            (id, business_id, action_type, dial, ceiling_sar, 
             max_price_increase_pct, max_price_decrease_pct, is_active, updated_by, updated_at)
            VALUES (gen_random_uuid(), :b, :a, :d, :ceil, :inc, :dec, true, :uid, NOW())
            ON CONFLICT (business_id, action_type) 
            DO UPDATE SET 
              dial = EXCLUDED.dial,
              ceiling_sar = EXCLUDED.ceiling_sar,
              max_price_increase_pct = EXCLUDED.max_price_increase_pct,
              max_price_decrease_pct = EXCLUDED.max_price_decrease_pct,
              is_active = EXCLUDED.is_active,
              updated_by = EXCLUDED.updated_by,
              updated_at = NOW()
        """), {
            "b": str(business_id),
            "a": action_type,
            "d": dial,
            "ceil": p.ceiling_sar,
            "inc": p.max_price_increase_pct,
            "dec": p.max_price_decrease_pct,
            "uid": str(current_user.id),
        })
    await db.commit()
    return {"ok": True, "updated": len(body.policies)}


# ── Manual scan trigger ───────────────────────────────

@router.post("/scan")
async def trigger_scan(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger Nazm planner – for testing / demo"""
    await assert_business_access(db, business_id, current_user)
    await require_feature_enabled(db, "agent_enabled", business_id=business_id)
    from app.services.nazm_planner import NazmPlanner
    planner = NazmPlanner(db)
    n = await planner.scan_business(business_id)
    return {"ok": True, "actions_created": n, "message": f"Nazm created {n} actions – check /feed"}


class AgentReasonRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    context: dict = Field(default_factory=dict)


class AutonomyEvaluateRequest(BaseModel):
    action_id: UUID
    business_id: UUID


class AutonomyDryRunRequest(BaseModel):
    action_id: UUID
    business_id: UUID


@router.post("/reason")
async def agent_reason(
    business_id: UUID,
    request: AgentReasonRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase 7: agent reasoning via the Unified Intelligence API.

    Lets the Nazm Agent consume the same intelligence surface as chat, dashboard,
    and the rest of the product.
    """
    await assert_business_access(db, business_id, current_user)
    await require_feature_enabled(db, "agent_enabled", business_id=business_id)
    client = IntelligenceAPIClient(db, business_id)
    result = await client.reason(question=request.question, context=request.context)
    await db.commit()
    return {
        "answer": result["answer"],
        "decision": result["decision"].ranked_action if result.get("decision") else None,
        "plan": {"goal": result["plan"].goal, "steps": result["plan"].steps} if result.get("plan") else None,
        "sources": result.get("sources", []),
    }


@router.post("/autonomy/evaluate")
async def evaluate_autonomy(
    request: AutonomyEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Evaluate an action's autonomy policy and auto-execute if safe."""
    await assert_business_access(db, request.business_id, current_user)
    ownership = await db.execute(text(
        "SELECT 1 FROM agent_actions WHERE id = :id AND business_id = :b"
    ), {"id": str(request.action_id), "b": str(request.business_id)})
    if not ownership.fetchone():
        raise HTTPException(404, "Action not found for business")

    await require_feature_enabled(db, "agent_enabled", business_id=request.business_id)
    result = await execute_if_autonomous(db, request.action_id, current_user.id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "Evaluation failed"))
    return result


@router.post("/actions/{action_id}/dry-run")
async def action_dry_run(
    action_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Preview what would happen if this action were approved/auto-executed."""
    await assert_business_access(db, business_id, current_user)
    ownership = await db.execute(text(
        "SELECT 1 FROM agent_actions WHERE id = :id AND business_id = :b"
    ), {"id": str(action_id), "b": str(business_id)})
    if not ownership.fetchone():
        raise HTTPException(404, "Action not found for business")

    await require_feature_enabled(db, "agent_enabled", business_id=business_id)
    return await dry_run_action(db, action_id)
