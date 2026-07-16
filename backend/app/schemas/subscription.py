from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class SubscriptionPlanInfo(BaseModel):
    plan: str
    name: str
    price_monthly: int = 0  # legacy field; annual pricing is used commercially
    price_annual_sar: Optional[int] = None
    ai_queries_per_day: int
    locations: int
    team_members: int
    pos_integrations: int
    features: list[str]


class SubscriptionResponse(BaseModel):
    id: UUID
    business_id: UUID
    plan: str
    status: str
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    trial_end: Optional[datetime]
    ai_queries_limit: int
    locations_limit: int
    team_members_limit: int
    pos_integrations_limit: int
    cancel_at_period_end: bool

    class Config:
        from_attributes = True


class UsageResponse(BaseModel):
    ai_queries: dict
    decisions: dict
    notifications: dict


class UsageHistoryItem(BaseModel):
    date: str
    ai_queries: int
    decisions: int
    notifications: int
    estimated_cost_cents: int


class BillingEventResponse(BaseModel):
    id: UUID
    event_type: str
    amount_cents: Optional[int]
    currency: str
    payload: dict
    processed_at: datetime

    class Config:
        from_attributes = True


class CheckoutSessionCreate(BaseModel):
    plan: str = Field(..., pattern=r'^(basic|pro|enterprise)$')


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class BillingPortalResponse(BaseModel):
    portal_url: str


PLANS = {
    "free": SubscriptionPlanInfo(
        plan="free",
        name="Free Money Audit",
        price_monthly=0,
        price_annual_sar=0,
        ai_queries_per_day=5,
        locations=1,
        team_members=1,
        pos_integrations=0,
        features=[
            "2 uploads/month",
            "1 Money Audit/month",
            "Dead stock + stockout risk report",
            "Margin leakage preview",
            "Mock WhatsApp approvals",
            "Recovery Match preview",
        ],
    ),
    "basic": SubscriptionPlanInfo(
        plan="basic",
        name="Small Retail",
        price_monthly=0,
        price_annual_sar=6900,
        ai_queries_per_day=20,
        locations=1,
        team_members=3,
        pos_integrations=0,
        features=[
            "Everything in Free Money Audit",
            "12 uploads/month",
            "Weekly Money Report",
            "Price Shield recommendations",
            "Shariah item guardrails",
            "Owner-ready recovery reporting",
        ],
    ),
    "pro": SubscriptionPlanInfo(
        plan="pro",
        name="Growing Retail",
        price_monthly=0,
        price_annual_sar=18000,
        ai_queries_per_day=100,
        locations=5,
        team_members=10,
        pos_integrations=2,
        features=[
            "Everything in Small Retail",
            "2-5 branch recovery reporting",
            "Branch transfer opportunities",
            "Live WhatsApp approvals",
            "Recovery Match",
            "Custom reports",
        ],
    ),
    "enterprise": SubscriptionPlanInfo(
        plan="enterprise",
        name="Large Chains",
        price_monthly=0,
        price_annual_sar=None,
        ai_queries_per_day=1000,
        locations=100,
        team_members=100,
        pos_integrations=20,
        features=[
            "Everything in Growing Retail",
            "Custom integrations",
            "Private deployment option",
            "Advanced Recovery Match",
            "Supplier marketplace readiness",
            "Dedicated onboarding",
        ],
    ),
}
