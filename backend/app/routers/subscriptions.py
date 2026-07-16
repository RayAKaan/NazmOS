from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime, timezone

from app.database.connection import get_db
from app.services.subscription_service import SubscriptionService, PLAN_CONFIG
from app.services.audit_service import AuditService
from app.services.multi_tenant import TenantContext
from app.schemas.subscription import (
    SubscriptionResponse, UsageResponse, UsageHistoryItem,
    BillingEventResponse, CheckoutSessionCreate, CheckoutSessionResponse,
    BillingPortalResponse, PLANS, SubscriptionPlanInfo,
)

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])


def get_current_tenant(request: Request) -> TenantContext:
    if not hasattr(request.state, "tenant_context"):
        raise HTTPException(401, "Not authenticated")
    return request.state.tenant_context


@router.get("/plans", response_model=list[SubscriptionPlanInfo])
async def list_plans():
    return list(PLANS.values())


@router.get("/current", response_model=SubscriptionResponse)
async def get_current_subscription(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    service = SubscriptionService(db)
    subscription = await service.get_subscription(tenant.business_id)
    
    if not subscription:
        subscription = await service.get_or_create_subscription(tenant.business_id)
    
    return subscription




@router.get("/snapshot")
async def get_plan_snapshot(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    service = SubscriptionService(db)
    return await service.get_plan_snapshot(tenant.business_id)


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    service = SubscriptionService(db)
    return await service.get_today_usage(tenant.business_id)


@router.get("/usage/history", response_model=list[UsageHistoryItem])
async def get_usage_history(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    service = SubscriptionService(db)
    history = await service.get_usage_history(tenant.business_id, days)
    return history


@router.post("/checkout")
async def create_checkout_session(
    data: CheckoutSessionCreate,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    if data.plan not in PLAN_CONFIG:
        raise HTTPException(400, "Invalid plan")
    
    return CheckoutSessionResponse(
        checkout_url=f"https://checkout.stripe.com/pay/demo_{data.plan}",
        session_id=f"cs_demo_{tenant.business_id}_{data.plan}",
    )


@router.post("/portal")
async def create_billing_portal(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return BillingPortalResponse(
        portal_url=f"https://billing.stripe.com/portal/demo_{tenant.business_id}",
    )


@router.post("/cancel")
async def cancel_subscription(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    service = SubscriptionService(db)
    subscription = await service.get_subscription(tenant.business_id)
    
    if not subscription:
        raise HTTPException(404, "No subscription found")
    
    subscription.cancel_at_period_end = True
    subscription.canceled_at = datetime.now(timezone.utc)
    subscription.cancellation_reason = "User requested cancellation"
    await db.commit()
    
    audit = AuditService(db)
    await audit.log_billing(
        business_id=tenant.business_id,
        event_type="subscription_canceled",
        new_value={"plan": subscription.plan, "canceled_at": str(subscription.canceled_at)},
    )
    
    return {"message": "Subscription will be canceled at period end"}


@router.post("/reactivate")
async def reactivate_subscription(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    service = SubscriptionService(db)
    subscription = await service.get_subscription(tenant.business_id)
    
    if not subscription:
        raise HTTPException(404, "No subscription found")
    
    subscription.cancel_at_period_end = False
    subscription.canceled_at = None
    await db.commit()
    
    return {"message": "Subscription reactivated"}


@router.get("/billing/events", response_model=list[BillingEventResponse])
async def get_billing_events(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    from sqlalchemy import select
    from app.database.models import BillingEvent
    
    result = await db.execute(
        select(BillingEvent)
        .where(BillingEvent.business_id == tenant.business_id)
        .order_by(BillingEvent.created_at.desc())
        .limit(limit)
    )
    
    return result.scalars().all()


@router.get("/features/{feature}")
async def check_feature_access(
    feature: str,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_current_tenant),
):
    service = SubscriptionService(db)
    has_access = await service.check_feature_access(tenant.business_id, feature)
    
    return {
        "feature": feature,
        "has_access": has_access,
        "plan_limits": (await service.get_plan_limits(tenant.business_id)).__dict__ if has_access else None,
    }
