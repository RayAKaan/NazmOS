"""Phase 6 real-pilot measurement primitives.

Keeps pilot baseline/outcome data durable while reusing existing deterministic
financial and learning infrastructure. No AI value is treated as financial truth.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import Business, MoneyAudit, MoneyAuditAction, OutcomeFeedback, PilotBaseline


def _num(value: Any) -> float:
    return float(value or 0)


async def create_or_refresh_baseline(db: AsyncSession, business_id: UUID, *, owner_id: UUID | None = None) -> PilotBaseline:
    audit = (await db.execute(
        select(MoneyAudit).where(MoneyAudit.business_id == business_id).order_by(MoneyAudit.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    actions = (await db.execute(
        select(func.count(MoneyAuditAction.id)).where(MoneyAuditAction.business_id == business_id)
    )).scalar_one() or 0
    snapshot = {
        "inventory_value_sar": _num(audit.inventory_value_sar if audit else 0),
        "capital_at_risk_sar": _num(audit.capital_at_risk_sar if audit else 0),
        "revenue_at_risk_sar": _num(audit.revenue_at_risk_sar if audit else 0),
        "gross_profit_at_risk_sar": _num(audit.gross_profit_at_risk_sar if audit else 0),
        "dead_stock_value_sar": _num(audit.dead_stock_value_sar if audit else 0),
        "overstock_value_sar": _num(audit.overstock_value_sar if audit else 0),
        "margin_leakage_sar": _num(audit.margin_leakage_sar if audit else 0),
        "stockout_risk_value_sar": _num(audit.stockout_risk_value_sar if audit else 0),
        "recommendation_count_at_baseline": int(actions),
        "audit_id": str(audit.id) if audit else None,
    }
    existing = (await db.execute(
        select(PilotBaseline).where(PilotBaseline.business_id == business_id, PilotBaseline.is_active.is_(True)).limit(1)
    )).scalar_one_or_none()
    if existing:
        existing.snapshot = snapshot
        existing.owner_id = owner_id or existing.owner_id
        existing.updated_at = datetime.now(timezone.utc)
        return existing
    row = PilotBaseline(business_id=business_id, owner_id=owner_id, snapshot=snapshot)
    db.add(row)
    await db.flush()
    return row


async def pilot_summary(db: AsyncSession, business_id: UUID) -> dict[str, Any]:
    baseline = (await db.execute(
        select(PilotBaseline).where(PilotBaseline.business_id == business_id, PilotBaseline.is_active.is_(True)).limit(1)
    )).scalar_one_or_none()
    latest = (await db.execute(
        select(MoneyAudit).where(MoneyAudit.business_id == business_id).order_by(MoneyAudit.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    outcomes = int((await db.execute(select(func.count(OutcomeFeedback.id)).where(OutcomeFeedback.business_id == business_id))).scalar_one() or 0)
    accepted = int((await db.execute(select(func.count(MoneyAuditAction.id)).where(MoneyAuditAction.business_id == business_id, MoneyAuditAction.status.in_(["approved", "completed"])))).scalar_one() or 0)
    return {
        "business_id": str(business_id),
        "baseline": baseline.snapshot if baseline else None,
        "current": {
            "inventory_value_sar": _num(latest.inventory_value_sar if latest else 0),
            "capital_at_risk_sar": _num(latest.capital_at_risk_sar if latest else 0),
            "revenue_at_risk_sar": _num(latest.revenue_at_risk_sar if latest else 0),
            "gross_profit_at_risk_sar": _num(latest.gross_profit_at_risk_sar if latest else 0),
            "dead_stock_value_sar": _num(latest.dead_stock_value_sar if latest else 0),
            "overstock_value_sar": _num(latest.overstock_value_sar if latest else 0),
            "margin_leakage_sar": _num(latest.margin_leakage_sar if latest else 0),
            "stockout_risk_value_sar": _num(latest.stockout_risk_value_sar if latest else 0),
        },
        "outcomes_recorded": outcomes,
        "approved_or_completed_actions": accepted,
    }


async def daily_brief(db: AsyncSession, business_id: UUID) -> dict[str, Any]:
    rows = (await db.execute(
        select(MoneyAuditAction).where(MoneyAuditAction.business_id == business_id, MoneyAuditAction.status.notin_(["completed", "rejected"]))
        .order_by(MoneyAuditAction.priority.asc(), MoneyAuditAction.created_at.desc()).limit(10)
    )).scalars().all()
    urgent = [r for r in rows if int(r.priority or 3) <= 2]
    return {
        "headline": "NazmOS — Today",
        "attention_count": len(urgent),
        "recommendations": [
            {"id": str(r.id), "title": r.title, "action_type": r.action_type,
             "priority": r.priority, "recoverable_low_sar": _num(r.recoverable_value_low_sar),
             "recoverable_high_sar": _num(r.recoverable_value_high_sar),
             "recovery_confidence": r.recovery_confidence}
            for r in rows
        ],
        "no_action_message": "No action required from the current evidence." if not rows else None,
    }
