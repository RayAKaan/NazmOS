"""
Retail guardrails API.

Kept intentionally narrow for NazmOS core Retail Recovery:
- inventory keyword screening
- anti-hoarding / fair pricing warning
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.middleware.auth_middleware import get_current_user
from app.database import User
from app.services.shariah_compliance import audit_inventory_halal_status, check_pricing_ethics_ihtikar

router = APIRouter(prefix="/api/v1/retail-guardrails", tags=["Retail Guardrails"])


class InventoryItemAuditSchema(BaseModel):
    sku: str = Field(..., example="DAT-SUK-01")
    name: str = Field(..., example="Al-Qassim Sukari Dates 1kg")
    description: Optional[str] = Field("", example="Fresh organic dates")


class PricingEthicsRequest(BaseModel):
    item_name: str = Field(..., example="Fresh Milk 1L")
    old_price: float = Field(..., example=6.0)
    new_price: float = Field(..., example=7.5)
    cost_increase_pct: float = Field(0.0, example=2.0)
    is_ramadan: bool = Field(False, example=True)


@router.post("/audit-inventory")
async def audit_inventory(items: List[InventoryItemAuditSchema], current_user: User = Depends(get_current_user)):
    items_dict = [item.model_dump() for item in items]
    return audit_inventory_halal_status(items_dict)


@router.post("/check-pricing-ethics")
async def check_pricing_ethics(req: PricingEthicsRequest, current_user: User = Depends(get_current_user)):
    return check_pricing_ethics_ihtikar(
        req.item_name,
        req.old_price,
        req.new_price,
        req.cost_increase_pct,
        req.is_ramadan,
    )


@router.get("/certificate")
async def get_guardrails_summary(business_name: str = Query("NazmOS Merchant"), current_user: User = Depends(get_current_user)):
    return {
        "issued_to": business_name,
        "guardrail_status": "Retail guardrails enabled",
        "inventory_keyword_screening": True,
        "anti_hoarding_price_warning": True,
        "note": "This is not a formal certification. NazmOS core focuses on retail recovery and safety guardrails.",
    }
