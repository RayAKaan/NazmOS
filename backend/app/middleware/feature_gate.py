from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.subscription_service import SubscriptionService
from app.config import get_settings


settings = get_settings()
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")


class FeatureLocked(HTTPException):
    def __init__(self, feature: str, required_plan: str = "Recovery Pilot"):
        super().__init__(
            status_code=402,
            detail={
                "code": "FEATURE_LOCKED",
                "feature": feature,
                "required_plan": required_plan,
                "message": "This feature is available after the Free Money Audit.",
                "cta": "Start 30-Day Recovery Pilot",
            },
        )


async def require_feature(
    db: AsyncSession,
    business_id: UUID | str,
    feature: str,
    required_plan: str = "Recovery Pilot",
) -> None:
    service = SubscriptionService(db)
    allowed = await service.check_feature_access(UUID(str(business_id)), feature)
    if not allowed:
        raise FeatureLocked(feature, required_plan)


async def enforce_upload_limit(db: AsyncSession, business_id: UUID | str) -> None:
    service = SubscriptionService(db)
    limits = await service.get_plan_limits(UUID(str(business_id)))
    # SQLite compatible replacement for date_trunc('month', NOW()).
    month_start_sql = "strftime('%Y-%m-01', 'now')" if _is_sqlite else "date_trunc('month', NOW())"
    res = await db.execute(text(f"""
        SELECT COUNT(*)
        FROM uploaded_files
        WHERE business_id = :business_id
          AND created_at >= {month_start_sql}
    """), {"business_id": str(business_id)})
    used = int(res.scalar() or 0)
    if used >= limits.uploads_per_month:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "UPLOAD_LIMIT_REACHED",
                "used": used,
                "limit": limits.uploads_per_month,
                "message": "Your Free Money Audit upload limit is reached.",
                "cta": "Start 30-Day Recovery Pilot",
            },
        )
