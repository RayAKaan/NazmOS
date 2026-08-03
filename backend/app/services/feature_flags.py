"""Dynamic feature-flag service.

Flags are evaluated in priority order:
1. Per-business override in feature_flag_overrides.
2. Plan-level gating in feature_flags.allowed_plans.
3. Global default in feature_flags.default_value.
4. Static env fallback (for bootstrapping before DB is available).

This lets NazmOS ship features behind killswitches, run canary rollouts by
plan, and disable a feature instantly for a specific merchant without a redeploy.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

_settings = get_settings()

# Map static env booleans to feature-flag keys so existing config still works
# when the dynamic table has not been seeded yet.
_ENV_FLAG_MAP = {
    "agent_enabled": _settings.AGENT_ENABLED,
    "agent_restock_enabled": _settings.AGENT_RESTOCK_ENABLED,
    "agent_pricing_enabled": _settings.AGENT_PRICING_ENABLED,
    "agent_cash_enabled": _settings.AGENT_CASH_ENABLED,
    "agent_staff_enabled": _settings.AGENT_STAFF_ENABLED,
    "chat_enabled": _settings.CHAT_ENABLED,
    "billing_enabled": _settings.BILLING_ENABLED,
    "supplier_network_enabled": _settings.SUPPLIER_NETWORK_ENABLED,
    "vertical_pharmacy": _settings.VERTICAL_PHARMACY,
    "vertical_food": _settings.VERTICAL_FOOD,
    "vertical_auto_parts": _settings.VERTICAL_AUTO_PARTS,
    "forecasting_enabled": _settings.ENABLE_FORECASTING,
    "anomaly_detection_enabled": _settings.ENABLE_ANOMALY_DETECTION,
}


async def is_feature_enabled(
    db: AsyncSession,
    key: str,
    business_id: Optional[str | UUID] = None,
    plan: Optional[str] = None,
) -> bool:
    """Evaluate a feature flag for a business/plan.

    Args:
        db: Active async DB session.
        key: Feature flag key (snake_case).
        business_id: Optional business UUID to check per-business override.
        plan: Optional subscription plan for plan-level gating.

    Returns:
        True if the feature is enabled.
    """
    # 1. Business override wins.
    if business_id:
        override = await db.execute(
            text("""
                SELECT o.value
                FROM feature_flag_overrides o
                JOIN feature_flags f ON f.id = o.feature_flag_id
                WHERE f.key = :key AND o.business_id = :business_id
            """),
            {"key": key, "business_id": str(business_id)},
        )
        row = override.fetchone()
        if row:
            return bool(row.value)

    # 2. Global flag definition (plan gating + default).
    flag = await db.execute(
        text("SELECT id, default_value, allowed_plans FROM feature_flags WHERE key = :key"),
        {"key": key},
    )
    row = flag.fetchone()
    if row:
        if plan and row.allowed_plans:
            allowed = {p.strip().lower() for p in row.allowed_plans.split(",") if p.strip()}
            if allowed and plan.lower() not in allowed:
                return False
        return bool(row.default_value)

    # 3. Static env fallback.
    return _ENV_FLAG_MAP.get(key, False)


async def set_business_override(
    db: AsyncSession,
    key: str,
    business_id: str | UUID,
    value: bool,
) -> None:
    """Create or update a per-business feature flag override."""
    await db.execute(
        text("""
            INSERT INTO feature_flag_overrides (id, feature_flag_id, business_id, value, created_at, updated_at)
            SELECT gen_random_uuid(), f.id, :business_id, :value, NOW(), NOW()
            FROM feature_flags f
            WHERE f.key = :key
            ON CONFLICT (feature_flag_id, business_id) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = NOW()
        """),
        {"key": key, "business_id": str(business_id), "value": value},
    )
    await db.commit()


async def seed_default_flags(db: AsyncSession) -> None:
    """Seed the flag table with NazmOS defaults if empty.

    Safe to run on every startup; existing keys are left untouched.
    """
    defaults = [
        ("agent_enabled", "Nazm Agent", "AI attention feed and agentic actions", True, None),
        ("agent_restock_enabled", "Agent Restock", "Automated restock suggestions", True, None),
        ("agent_pricing_enabled", "Agent Pricing", "Automated pricing suggestions", True, None),
        ("agent_cash_enabled", "Agent Cash", "Cash flow alerts", True, None),
        ("agent_staff_enabled", "Agent Staff", "Staff scheduling alerts", True, None),
        ("chat_enabled", "Baseer Chat", "Conversational AI copilot", True, None),
        ("billing_enabled", "Billing", "Subscription and usage billing", True, None),
        ("supplier_network_enabled", "Supplier Network", "Retailer-to-retailer recovery match", True, None),
        ("vertical_pharmacy", "Pharmacy Module", "FEFO/SFDA pharmacy features", True, "enterprise"),
        ("vertical_food", "Food Module", "Recipe BOM and food service features", False, None),
        ("vertical_auto_parts", "Auto Parts Module", "Parts compatibility features", False, None),
        ("forecasting_enabled", "Forecasting", "Prophet-based demand forecasts", True, None),
        ("anomaly_detection_enabled", "Anomaly Detection", "Sales/inventory anomaly alerts", True, None),
    ]
    for key, name, description, default, plans in defaults:
        await db.execute(
            text("""
                INSERT INTO feature_flags (id, key, name, description, default_value, allowed_plans, created_at, updated_at)
                VALUES (gen_random_uuid(), :key, :name, :description, :default_value, :allowed_plans, NOW(), NOW())
                ON CONFLICT (key) DO NOTHING
            """),
            {
                "key": key,
                "name": name,
                "description": description,
                "default_value": default,
                "allowed_plans": plans,
            },
        )
    await db.commit()


async def require_feature_enabled(
    db: AsyncSession,
    key: str,
    business_id: Optional[str | UUID] = None,
    plan: Optional[str] = None,
) -> None:
    """Raise 403 if a feature flag is disabled for the given scope.

    Falls back to static env values when the dynamic table is empty, so the
    backend keeps working before flags have been seeded.
    """
    if not await is_feature_enabled(db, key, business_id=business_id, plan=plan):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FEATURE_DISABLED",
                "feature": key,
                "message": f"Feature '{key}' is currently disabled for this business.",
            },
        )
