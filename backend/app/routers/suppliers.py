"""
Supplier Network API – KSA
Read-only in v1.5 – tracks POs for network effect
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.config import get_settings

router = APIRouter(prefix="/api/v1/suppliers", tags=["Suppliers"])
settings = get_settings()


@router.get("")
async def list_suppliers(
    city: str = None,
    category: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List suppliers – demo-seeded only outside production or when explicitly enabled."""
    count = await db.execute(text("SELECT COUNT(*) FROM suppliers"))
    allow_demo_seed = getattr(settings, "ALLOW_DEMO_SEED", False) or settings.ENVIRONMENT != "production"
    if count.scalar() == 0 and allow_demo_seed:
        # Fictional demo entities only. Never attribute invented contact details to real companies.
        sa_suppliers = [
            ("مورد ألبان الرياض التجريبي", "Riyadh Demo Dairy Distributor", "Riyadh", "dairy", "+966500000001", "+966500000001", 1),
            ("تمور القصيم التجريبية", "Qassim Demo Date Farms", "Buraidah", "dates_wholesale", "+966500000002", "+966500000002", 1),
            ("مورد أغذية نجد التجريبي", "Najd Demo Food Supply", "Riyadh", "food_wholesale", "+966500000003", "+966500000003", 2),
            ("موزع صيدليات تجريبي", "Demo Pharmacy Distributor", "Dammam", "pharma", "+966500000004", "+966500000004", 2),
        ]
        for ar, en, city_, cat, phone, wa, lead in sa_suppliers:
            await db.execute(text("""
                INSERT INTO suppliers (id, name_ar, name_en, city, category, phone, whatsapp_number, lead_time_days, is_active, is_verified)
                VALUES (gen_random_uuid(), :ar, :en, :city, :cat, :phone, :wa, :lead, true, true)
                ON CONFLICT DO NOTHING
            """), {"ar": ar, "en": en, "city": city_, "cat": cat, "phone": phone, "wa": wa, "lead": lead})
        await db.commit()
    
    where = ["is_active = true"]
    params = {}
    if city:
        where.append("city = :city")
        params["city"] = city
    if category:
        where.append("category = :category")
        params["category"] = category
    
    q = f"""
        SELECT id, name_ar, name_en, city, category, phone, whatsapp_number,
               lead_time_days, total_monthly_volume_sar
        FROM suppliers
        WHERE {' AND '.join(where)}
        ORDER BY total_monthly_volume_sar DESC NULLS LAST, name_en
        LIMIT 100
    """  # nosec B608
    res = await db.execute(text(q), params)
    rows = res.fetchall()
    
    return {
        "suppliers": [
            {
                "id": str(r.id),
                "name_ar": r.name_ar,
                "name_en": r.name_en,
                "city": r.city,
                "category": r.category,
                "phone": r.phone,
                "whatsapp_number": r.whatsapp_number,
                "lead_time_days": r.lead_time_days,
                "total_orders": 0,
                "total_volume_sar": float(r.total_monthly_volume_sar or 0),
            }
            for r in rows
        ]
    }


@router.get("/purchase-orders")
async def list_pos(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List purchase orders for a business"""
    await assert_business_access(db, business_id, current_user)
    res = await db.execute(text("""
        SELECT po.*, s.name_en as supplier_name, s.name_ar as supplier_name_ar
        FROM purchase_orders po
        LEFT JOIN suppliers s ON s.id = po.supplier_id
        WHERE po.business_id = :b
        ORDER BY po.created_at DESC
        LIMIT 50
    """), {"b": str(business_id)})
    rows = res.fetchall()
    return {
        "orders": [
            {
                "id": str(r.id),
                "po_number": r.po_number,
                "supplier_name": r.supplier_name_ar or r.supplier_name,
                "status": r.status,
                "total_sar": float(r.total_sar or 0),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "expected_delivery": r.expected_delivery.isoformat() if r.expected_delivery else None,
            }
            for r in rows
        ]
    }
