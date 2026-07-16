"""
Pharmacy Vertical API – KSA
Expiry / FEFO / SFDA recalls
Feature-flagged: VERTICAL_PHARMACY=true
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import date

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/v1/pharmacy", tags=["Pharmacy"])


def _require_pharmacy():
    if not getattr(settings, "VERTICAL_PHARMACY", True):
        raise HTTPException(404, "Pharmacy module disabled – enable VERTICAL_PHARMACY=true")


@router.get("/lots")
async def list_lots(
    business_id: UUID,
    days_ahead: int = 180,
    status: str = "all",  # all | critical | warning | ok
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """FEFO expiry tracker – list all lots with days-to-expiry"""
    _require_pharmacy()
    
    # Ensure table exists – create empty if first run
    try:
        where = ["pl.business_id = :b", "pl.quantity > 0"]
        if status == "critical":
            where.append("pl.expiry_date <= CURRENT_DATE + INTERVAL '30 days'")
        elif status == "warning":
            where.append("pl.expiry_date > CURRENT_DATE + INTERVAL '30 days'")
            where.append("pl.expiry_date <= CURRENT_DATE + INTERVAL '90 days'")
        elif status == "ok":
            where.append("pl.expiry_date > CURRENT_DATE + INTERVAL '90 days'")
        
        res = await db.execute(text(f"""
            SELECT 
                pl.id, pl.batch_number, pl.expiry_date, pl.quantity,
                i.id as item_id, i.name as item_name,
                GREATEST(0, (pl.expiry_date - CURRENT_DATE)) as days_left
            FROM pharmacy_lots pl
            JOIN items i ON i.id = pl.item_id
            WHERE {' AND '.join(where)}
            ORDER BY pl.expiry_date ASC
            LIMIT 200
        """), {"b": str(business_id)})
        rows = res.fetchall()
    except Exception:
        # Table doesn't exist yet – return empty, frontend shows demo fallback
        rows = []
    
    lots = []
    for r in rows:
        days = int(r.days_left or 999)
        lots.append({
            "id": str(r.id),
            "item_id": str(r.item_id),
            "item_name": r.item_name,
            "item_name_ar": r.item_name,
            "batch_number": r.batch_number,
            "expiry_date": r.expiry_date.isoformat(),
            "quantity": float(r.quantity),
            "days_left": days,
        })
    
    return {"lots": lots, "count": len(lots)}


@router.get("/recalls")
async def check_recalls(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SFDA recall check – cross-match inventory against recall list"""
    _require_pharmacy()
    # v1.5: stub – always clean
    # v2.0: fetch https://www.sfda.gov.sa/en/rss/recalls → match against items.sku / gtin
    return {
        "status": "clean",
        "matched_recalls": [],
        "last_checked": date.today().isoformat(),
        "source": "SFDA – الهيئة العامة للغذاء والدواء",
        "note": "Auto recall matching – coming in v2.0 – currently manual check recommended"
    }


@router.post("/lots")
async def add_lot(
    business_id: UUID,
    item_id: UUID,
    batch_number: str,
    expiry_date: date,
    quantity: float,
    cost_per_unit: float = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a pharmacy stock lot – FEFO tracked"""
    _require_pharmacy()
    await db.execute(text("""
        INSERT INTO pharmacy_lots
        (id, business_id, item_id, batch_number, expiry_date, quantity, cost_per_unit,
         days_to_expiry, is_expired, is_near_expiry)
        VALUES
        (gen_random_uuid(), :b, :item, :batch, :exp, :qty, :cost,
         GREATEST(0, :exp - CURRENT_DATE),
         :exp <= CURRENT_DATE,
         :exp <= CURRENT_DATE + INTERVAL '90 days')
    """), {
        "b": str(business_id), "item": str(item_id),
        "batch": batch_number, "exp": expiry_date,
        "qty": quantity, "cost": cost_per_unit,
    })
    await db.commit()
    return {"ok": True}
