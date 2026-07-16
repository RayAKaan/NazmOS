"""
Nazm Agent API – KSA
Attention feed + approval queue + autonomy dial
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession
import json
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.services.agent_action_executor import approve_agent_action, reject_agent_action

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


@router.put("/autonomy")
async def set_autonomy(
    business_id: UUID,
    policies: list,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update autonomy dial – 0-100 per action_type"""
    await assert_business_access(db, business_id, current_user)
    for p in policies:
        action_type = p["action_type"]
        dial = max(0, min(100, int(p.get("dial", 50))))
        
        # Enforce safety ceilings – pricing never >50 without explicit override
        if action_type.startswith("pricing") and dial > 50:
            dial = 50
        
        await db.execute(text("""
            INSERT INTO autonomy_policies 
            (id, business_id, action_type, dial, ceiling_sar, 
             max_price_increase_pct, max_price_decrease_pct, updated_by, updated_at)
            VALUES (gen_random_uuid(), :b, :a, :d, :ceil, :inc, :dec, :uid, NOW())
            ON CONFLICT (business_id, action_type) 
            DO UPDATE SET 
              dial = EXCLUDED.dial,
              ceiling_sar = EXCLUDED.ceiling_sar,
              max_price_increase_pct = EXCLUDED.max_price_increase_pct,
              max_price_decrease_pct = EXCLUDED.max_price_decrease_pct,
              updated_by = EXCLUDED.updated_by,
              updated_at = NOW()
        """), {
            "b": str(business_id),
            "a": action_type,
            "d": dial,
            "ceil": p.get("ceiling_sar"),
            "inc": p.get("max_price_increase_pct"),
            "dec": p.get("max_price_decrease_pct"),
            "uid": str(current_user.id),
        })
    await db.commit()
    return {"ok": True, "updated": len(policies)}


# ── Manual scan trigger ───────────────────────────────

@router.post("/scan")
async def trigger_scan(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger Nazm planner – for testing / demo"""
    await assert_business_access(db, business_id, current_user)
    from app.services.nazm_planner import NazmPlanner
    planner = NazmPlanner(db)
    n = await planner.scan_business(business_id)
    return {"ok": True, "actions_created": n, "message": f"Nazm created {n} actions – check /feed"}
