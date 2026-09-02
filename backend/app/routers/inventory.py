from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from app.database import get_db, User
from app.schemas.inventory import (
    InventoryResponse,
    ItemDetailResponse,
    RestockRequest,
    RestockResponse,
)
from app.services.analytics_service import get_inventory_list, get_item_detail
from app.services.inventory_service import restock_item
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access

router = APIRouter(prefix="/inventory", tags=["Inventory"])


async def _verify_business_access(db: AsyncSession, business_id: UUID, user: User):
    """Verify ownership or active team membership via the shared gate.

    Also records denials to the AuditLog.
    """
    await assert_business_access(db, business_id, user)


@router.get("", response_model=InventoryResponse)
async def get_inventory(
    business_id: UUID = Query(...),
    status: str = Query(default="all"),
    category: str = Query(default="all"),
    search: str = Query(default=""),
    sort: str = Query(default="days_left"),
    order: str = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_business_access(db, business_id, current_user)
    return await get_inventory_list(
        db, business_id, status, category, search, sort, order, page, limit
    )


@router.get("/{item_id}/detail", response_model=ItemDetailResponse)
async def get_detail(
    item_id: UUID,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_business_access(db, business_id, current_user)
    return await get_item_detail(db, business_id, item_id)


@router.post("/restock", response_model=RestockResponse)
async def restock(
    data: RestockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Tenant gate: the request body's business_id is client-supplied and must
    # not be trusted for DB scoping until the caller proves access to it.
    await _verify_business_access(db, data.business_id, current_user)
    return await restock_item(db, data)
