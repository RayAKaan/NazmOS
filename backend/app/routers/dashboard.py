from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from app.database import get_db, User
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    AlertsResponse,
    SalesTrendResponse,
    TopProductsResponse,
    DeadStockResponse,
    HourlyPatternResponse,
    CategoryBreakdownResponse,
)
from app.services.analytics_service import (
    get_dashboard_summary,
    get_sales_trend,
    get_top_products,
    get_dead_stock,
    get_hourly_pattern,
    get_category_breakdown,
    get_dashboard_alerts,
)
from app.services.intelligence_api_client import IntelligenceAPIClient
from app.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


async def _verify_business_access(db: AsyncSession, business_id: UUID, user: User):
    """KSA PDPL – verify user owns/has access to business"""
    result = await db.execute(
        text("SELECT owner_id FROM businesses WHERE id = :id"),
        {"id": str(business_id)}
    )
    biz = result.fetchone()
    if not biz:
        raise HTTPException(404, "Business not found")
    if str(biz.owner_id) == str(user.id):
        return
    tm = await db.execute(text(
        "SELECT 1 FROM team_members WHERE business_id = :bid AND user_id = :uid AND is_active = true"
    ), {"bid": str(business_id), "uid": str(user.id)})
    if tm.fetchone():
        return
    raise HTTPException(403, "Not authorized for this business")


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_summary(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_business_access(db, business_id, current_user)
    return await get_dashboard_summary(db, business_id)


@router.get("/intelligence-summary")
async def get_intelligence_summary(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard summary powered by the Unified Intelligence API.

    This endpoint demonstrates how existing NazmOS applications can consume the
    intelligence layer instead of querying raw SQL directly.
    """
    await _verify_business_access(db, business_id, current_user)
    client = IntelligenceAPIClient(db, business_id)
    result = await client.analyze(query="What should I focus on today?")
    decision = result.get("decision")
    return {
        "summary": result["summary"],
        "recent_event_count": result["recent_event_count"],
        "top_action": decision.ranked_action if decision else None,
        "sources": result["sources"],
    }


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_business_access(db, business_id, current_user)
    return await get_dashboard_alerts(db, business_id)


@router.get("/sales-trend", response_model=SalesTrendResponse)
async def get_sales(
    business_id: UUID = Query(...),
    period: int = Query(default=30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_business_access(db, business_id, current_user)
    return await get_sales_trend(db, business_id, period)


@router.get("/top-products", response_model=TopProductsResponse)
async def get_top(
    business_id: UUID = Query(...),
    period: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_business_access(db, business_id, current_user)
    return await get_top_products(db, business_id, period, limit)


@router.get("/dead-stock", response_model=DeadStockResponse)
async def get_dead(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_business_access(db, business_id, current_user)
    return await get_dead_stock(db, business_id)


@router.get("/hourly-pattern", response_model=HourlyPatternResponse)
async def get_hourly(
    business_id: UUID = Query(...),
    period: int = Query(default=30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_business_access(db, business_id, current_user)
    return await get_hourly_pattern(db, business_id, period)


@router.get("/category-breakdown", response_model=CategoryBreakdownResponse)
async def get_categories(
    business_id: UUID = Query(...),
    period: int = Query(default=30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_business_access(db, business_id, current_user)
    return await get_category_breakdown(db, business_id, period)
