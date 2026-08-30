"""Operational health + data freshness (Phase 10, §25–28).

A deterministic, operator-facing (and merchant-simplified) health view. Determines whether
NazmOS itself is HEALTHY / DEGRADED / REQUIRES_RECONCILIATION, and surfaces stale data
inputs that could make recommendations less accurate. Never fabricates timestamps (§28).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

_settings = get_settings()

# Freshness thresholds (hours). Configurable; conservative defaults, not invented arbitrarily
# — they map to the existing forecast-cache / upload-cleanup cadences.
FRESH_INVENTORY_HOURS = float(getattr(_settings, "FRESH_INVENTORY_HOURS", 96))
FRESH_SALES_HOURS = float(getattr(_settings, "FRESH_SALES_HOURS", 48))
FRESH_SUPPLIER_PRICE_HOURS = float(getattr(_settings, "FRESH_SUPPLIER_PRICE_HOURS", 24 * 30))


def freshness_state(age_hours: float | None, threshold_hours: float) -> str:
    """§Part 7: deterministic four-state freshness model.

    fresh  = age <= threshold
    aging  = threshold < age <= 2× threshold
    stale  = age > 2× threshold
    unknown= no timestamp (never fabricate a timestamp)
    """
    if age_hours is None:
        return "unknown"
    if age_hours <= threshold_hours:
        return "fresh"
    if age_hours <= threshold_hours * 2:
        return "aging"
    return "stale"


def _age_hours(v: Any, now: datetime | None = None) -> float | None:
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v)
        except ValueError:
            return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - v).total_seconds() / 3600.0)


async def data_freshness(db: AsyncSession, business_id: UUID | str, now: datetime | None = None) -> dict[str, Any]:
    """Freshness of the inputs that feed recommendations, with explicit 'unknown' where
    no timestamp exists. `now` is injectable for virtual-time tests (§Part 2)."""
    inv = await db.execute(text("SELECT MAX(updated_at) FROM inventory WHERE business_id = :b"),
                           {"b": str(business_id)})
    sales = await db.execute(text("SELECT MAX(transaction_at) FROM transactions WHERE business_id = :b"),
                             {"b": str(business_id)})
    sp = await db.execute(text("SELECT MAX(created_at) FROM supplier_prices WHERE business_id = :b"),
                          {"b": str(business_id)})

    inv_age = _age_hours(inv.scalar(), now)
    sales_age = _age_hours(sales.scalar(), now)
    sp_age = _age_hours(sp.scalar(), now)

    def _fresh(label: str, age: float | None, threshold: float) -> dict[str, Any]:
        state = freshness_state(age, threshold)
        return {
            "label": label,
            "age_hours": round(age, 1) if age is not None else None,
            "state": state,
            "fresh": state == "fresh",
            "stale": state == "stale",
            "aging": state == "aging",
            "unknown": state == "unknown",
        }

    return {
        "inventory": _fresh("Inventory", inv_age, FRESH_INVENTORY_HOURS),
        "sales": _fresh("Sales", sales_age, FRESH_SALES_HOURS),
        "supplier_prices": _fresh("Supplier prices", sp_age, FRESH_SUPPLIER_PRICE_HOURS),
    }


async def operational_health(db: AsyncSession, business_id: UUID | str, now: datetime | None = None) -> dict[str, Any]:
    """HEALTHY / DEGRADED / REQUIRES_RECONCILIATION, plus learning-reconciliation gap count.
    `now` injectable for virtual-time tests."""
    freshness = await data_freshness(db, business_id, now=now)

    # Reconciliation gap: terminal actions missing either LearnedOutcome or OutcomeFeedback.
    gap = await db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM agent_actions a
             LEFT JOIN learned_outcomes lo ON lo.agent_action_id = a.id
             WHERE a.business_id = :b
               AND a.status IN ('approved','executed','auto_executed','rejected','failed')
               AND lo.id IS NULL) AS missing_learned,
          (SELECT COUNT(*) FROM agent_actions a
             LEFT JOIN outcome_feedback of ON of.agent_action_id = a.id
             WHERE a.business_id = :b
               AND a.status IN ('approved','executed','auto_executed','rejected','failed')
               AND of.id IS NULL) AS missing_feedback
    """), {"b": str(business_id)})
    row = gap.fetchone()
    missing_learned = int(row.missing_learned or 0)
    missing_feedback = int(row.missing_feedback or 0)

    # Failed executions (executed=False but approved/auto) = degraded execution.
    failed_exec = await db.execute(text("""
        SELECT COUNT(*) FROM agent_actions
        WHERE business_id = :b AND status IN ('failed')
    """), {"b": str(business_id)})
    failed = int(failed_exec.scalar() or 0)

    reconciliation_gap = missing_learned + missing_feedback
    stale_any = any(v.get("stale") for v in freshness.values())

    if reconciliation_gap > 0:
        status = "requires_reconciliation"
    elif stale_any or failed > 0:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "reconciliation": {
            "missing_learned_outcomes": missing_learned,
            "missing_outcome_feedback": missing_feedback,
        },
        "failed_executions": failed,
        "data_freshness": freshness,
        "merchant_summary": _merchant_summary(status, freshness),
    }


def _merchant_summary(status: str, freshness: dict[str, Any]) -> str:
    """§26: a simple, non-technical merchant-facing status line."""
    if status == "healthy":
        return "NazmOS is healthy."
    parts = []
    for v in freshness.values():
        if v.get("stale"):
            parts.append(f"{v['label'].lower()} hasn't been updated for {int(v['age_hours'])} hours")
    if status == "requires_reconciliation":
        parts.append("some learning records need repair")
    if not parts:
        parts.append("some data may be less accurate")
    return "NazmOS needs attention: " + "; ".join(parts) + "."
