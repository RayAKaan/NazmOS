from typing import Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import structlog

from app.database.models import Subscription, SubscriptionUsage, Business

logger = structlog.get_logger(__name__)


@dataclass
class PlanLimits:
    # Commercial identity
    name: str
    annual_price_sar: int | None

    # Hard limits
    branches: int
    max_skus: int
    uploads_per_month: int
    money_audits_per_month: int
    ai_queries_per_day: int
    team_members: int
    pos_integrations: int

    # Core Retail Recovery features
    forecasting: bool
    pricing_optimization: bool
    team_management: bool
    multi_branch_rebalancing: bool
    dead_stock_detection: bool
    stockout_risk: bool
    margin_leakage: bool
    weekly_money_report: bool
    mock_whatsapp: bool
    live_whatsapp: bool

    # R2R moat / Recovery Match
    recovery_match_preview: bool
    recovery_match: bool
    recovery_match_contact_reveal: bool
    supplier_directory: bool
    supplier_marketplace: bool

    # Advanced/admin
    api_access: bool
    custom_reports: bool

    @property
    def locations(self) -> int:
        return self.branches


PLAN_CONFIG = {
    "free": PlanLimits(
        name="Free Money Audit",
        annual_price_sar=0,
        branches=1,
        max_skus=500,
        uploads_per_month=2,
        money_audits_per_month=1,
        ai_queries_per_day=5,
        team_members=1,
        pos_integrations=0,
        forecasting=True,
        pricing_optimization=True,
        team_management=False,
        multi_branch_rebalancing=False,
        dead_stock_detection=True,
        stockout_risk=True,
        margin_leakage=True,
        weekly_money_report=False,
        mock_whatsapp=True,
        live_whatsapp=False,
        recovery_match_preview=True,
        recovery_match=False,
        recovery_match_contact_reveal=False,
        supplier_directory=True,
        supplier_marketplace=False,
        api_access=False,
        custom_reports=False,
    ),
    "basic": PlanLimits(
        name="Small Retail",
        annual_price_sar=6900,
        branches=1,
        max_skus=750,
        uploads_per_month=12,
        money_audits_per_month=4,
        ai_queries_per_day=20,
        team_members=3,
        pos_integrations=0,
        forecasting=True,
        pricing_optimization=True,
        team_management=True,
        multi_branch_rebalancing=False,
        dead_stock_detection=True,
        stockout_risk=True,
        margin_leakage=True,
        weekly_money_report=True,
        mock_whatsapp=True,
        live_whatsapp=False,
        recovery_match_preview=True,
        recovery_match=False,
        recovery_match_contact_reveal=False,
        supplier_directory=True,
        supplier_marketplace=False,
        api_access=False,
        custom_reports=False,
    ),
    "pro": PlanLimits(
        name="Growing Retail",
        annual_price_sar=18000,
        branches=5,
        max_skus=5000,
        uploads_per_month=100,
        money_audits_per_month=12,
        ai_queries_per_day=100,
        team_members=10,
        pos_integrations=2,
        forecasting=True,
        pricing_optimization=True,
        team_management=True,
        multi_branch_rebalancing=True,
        dead_stock_detection=True,
        stockout_risk=True,
        margin_leakage=True,
        weekly_money_report=True,
        mock_whatsapp=True,
        live_whatsapp=True,
        recovery_match_preview=True,
        recovery_match=True,
        recovery_match_contact_reveal=True,
        supplier_directory=True,
        supplier_marketplace=False,  # full marketplace later, after manual Recovery Match validation
        api_access=False,
        custom_reports=True,
    ),
    "enterprise": PlanLimits(
        name="Large Chains",
        annual_price_sar=None,
        branches=999,
        max_skus=999999,
        uploads_per_month=999999,
        money_audits_per_month=999999,
        ai_queries_per_day=1000,
        team_members=100,
        pos_integrations=20,
        forecasting=True,
        pricing_optimization=True,
        team_management=True,
        multi_branch_rebalancing=True,
        dead_stock_detection=True,
        stockout_risk=True,
        margin_leakage=True,
        weekly_money_report=True,
        mock_whatsapp=True,
        live_whatsapp=True,
        recovery_match_preview=True,
        recovery_match=True,
        recovery_match_contact_reveal=True,
        supplier_directory=True,
        supplier_marketplace=True,
        api_access=True,
        custom_reports=True,
    ),
}

FEATURE_ATTRS = {
    "forecasting": "forecasting",
    "pricing_optimization": "pricing_optimization",
    "team_management": "team_management",
    "multi_branch_rebalancing": "multi_branch_rebalancing",
    "dead_stock_detection": "dead_stock_detection",
    "stockout_risk": "stockout_risk",
    "margin_leakage": "margin_leakage",
    "weekly_money_report": "weekly_money_report",
    "mock_whatsapp": "mock_whatsapp",
    "live_whatsapp": "live_whatsapp",
    "recovery_match_preview": "recovery_match_preview",
    "recovery_match": "recovery_match",
    "recovery_match_contact_reveal": "recovery_match_contact_reveal",
    "supplier_directory": "supplier_directory",
    "supplier_marketplace": "supplier_marketplace",
    "api_access": "api_access",
    "custom_reports": "custom_reports",
    "pos_integration": "pos_integrations",  # backward-compatible older name
}


def recommend_plan(branches: int, sku_count: int, pain: str | None = None) -> str:
    if branches <= 1 and sku_count <= 750:
        return "basic"
    if 2 <= branches <= 5:
        return "pro"
    return "enterprise"


class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_subscription(self, business_id: UUID) -> Subscription:
        result = await self.db.execute(select(Subscription).where(Subscription.business_id == business_id))
        subscription = result.scalar_one_or_none()
        if not subscription:
            free = PLAN_CONFIG["free"]
            subscription = Subscription(
                business_id=business_id,
                plan="free",
                status="active",
                ai_queries_limit=free.ai_queries_per_day,
                locations_limit=free.branches,
                team_members_limit=free.team_members,
                pos_integrations_limit=free.pos_integrations,
            )
            self.db.add(subscription)
            await self.db.commit()
            await self.db.refresh(subscription)
            logger.info("subscription_created", business_id=str(business_id), plan="free_money_audit")
        return subscription

    async def get_subscription(self, business_id: UUID) -> Optional[Subscription]:
        result = await self.db.execute(select(Subscription).where(Subscription.business_id == business_id))
        return result.scalar_one_or_none()

    async def get_plan_limits(self, business_id: UUID) -> PlanLimits:
        subscription = await self.get_or_create_subscription(business_id)
        return PLAN_CONFIG.get(subscription.plan, PLAN_CONFIG["free"])

    async def get_plan_snapshot(self, business_id: UUID) -> dict:
        subscription = await self.get_or_create_subscription(business_id)
        limits = await self.get_plan_limits(business_id)
        return {
            "plan": subscription.plan,
            "name": limits.name,
            "annual_price_sar": limits.annual_price_sar,
            "is_free": subscription.plan == "free",
            "status": subscription.status,
            "upgrade_cta": "Start 30-Day Recovery Pilot" if subscription.plan == "free" else None,
            "limits": limits.__dict__,
        }

    async def check_usage_limit(self, business_id: UUID, usage_type: str, increment: int = 1) -> tuple[bool, int, int]:
        subscription = await self.get_or_create_subscription(business_id)
        today = datetime.now(timezone.utc).date()
        result = await self.db.execute(
            select(SubscriptionUsage).where(
                and_(SubscriptionUsage.subscription_id == subscription.id, SubscriptionUsage.usage_date == today)
            )
        )
        usage = result.scalar_one_or_none()
        if not usage:
            usage = SubscriptionUsage(subscription_id=subscription.id, usage_date=today)
            self.db.add(usage)
            await self.db.commit()
            await self.db.refresh(usage)

        if usage_type == "ai_query":
            current = usage.ai_queries_used
            limit = subscription.ai_queries_limit
        elif usage_type == "decision":
            current = usage.decisions_applied
            limit = 1000
        elif usage_type == "notification":
            current = usage.notifications_sent
            limit = 1000
        else:
            return True, 0, 1000

        within_limit = (current + increment) <= limit
        if not within_limit:
            logger.warning("usage_limit_exceeded", business_id=str(business_id), usage_type=usage_type, current=current, limit=limit)
        return within_limit, current, limit

    async def increment_usage(self, business_id: UUID, usage_type: str, tokens: int = 0) -> SubscriptionUsage:
        subscription = await self.get_or_create_subscription(business_id)
        today = datetime.now(timezone.utc).date()
        result = await self.db.execute(
            select(SubscriptionUsage).where(
                and_(SubscriptionUsage.subscription_id == subscription.id, SubscriptionUsage.usage_date == today)
            )
        )
        usage = result.scalar_one_or_none()
        if not usage:
            usage = SubscriptionUsage(subscription_id=subscription.id, usage_date=today)
            self.db.add(usage)

        if usage_type == "ai_query":
            usage.ai_queries_used += 1
            if tokens > 0:
                usage.llm_prompt_tokens += tokens // 2
                usage.llm_completion_tokens += tokens // 2
                usage.estimated_cost_cents += int(tokens * 0.00001 * 100)
        elif usage_type == "decision":
            usage.decisions_applied += 1
        elif usage_type == "notification":
            usage.notifications_sent += 1

        await self.db.commit()
        await self.db.refresh(usage)
        return usage

    async def get_today_usage(self, business_id: UUID) -> dict:
        subscription = await self.get_or_create_subscription(business_id)
        today = datetime.now(timezone.utc).date()
        result = await self.db.execute(
            select(SubscriptionUsage).where(
                and_(SubscriptionUsage.subscription_id == subscription.id, SubscriptionUsage.usage_date == today)
            )
        )
        usage = result.scalar_one_or_none()
        used_ai = usage.ai_queries_used if usage else 0
        used_decisions = usage.decisions_applied if usage else 0
        used_notifications = usage.notifications_sent if usage else 0
        return {
            "ai_queries": {
                "used": used_ai,
                "limit": subscription.ai_queries_limit,
                "percent": round((used_ai / subscription.ai_queries_limit) * 100, 1) if subscription.ai_queries_limit > 0 else 0,
            },
            "decisions": {"used": used_decisions, "limit": 1000, "percent": round(used_decisions / 10, 1)},
            "notifications": {"used": used_notifications, "limit": 1000, "percent": round(used_notifications / 10, 1)},
        }

    async def get_usage_history(self, business_id: UUID, days: int = 30) -> list[dict]:
        subscription = await self.get_or_create_subscription(business_id)
        start_date = datetime.now(timezone.utc).date() - timedelta(days=days)
        result = await self.db.execute(
            select(SubscriptionUsage)
            .where(and_(SubscriptionUsage.subscription_id == subscription.id, SubscriptionUsage.usage_date >= start_date))
            .order_by(SubscriptionUsage.usage_date.desc())
        )
        return [
            {
                "date": str(usage.usage_date),
                "ai_queries": usage.ai_queries_used,
                "decisions": usage.decisions_applied,
                "notifications": usage.notifications_sent,
                "estimated_cost_cents": usage.estimated_cost_cents,
            }
            for usage in result.scalars().all()
        ]

    async def check_feature_access(self, business_id: UUID, feature: str) -> bool:
        limits = await self.get_plan_limits(business_id)
        attr = FEATURE_ATTRS.get(feature)
        if not attr:
            return False
        value = getattr(limits, attr, False)
        if isinstance(value, bool):
            return value
        return bool(value)

    async def count_locations(self, business_id: UUID) -> int:
        business = await self.db.get(Business, business_id)
        if not business:
            return 0
        if business.organization_id:
            result = await self.db.execute(select(func.count(Business.id)).where(Business.organization_id == business.organization_id))
        else:
            result = await self.db.execute(select(func.count(Business.id)).where(Business.owner_id == business.owner_id))
        return result.scalar() or 0
