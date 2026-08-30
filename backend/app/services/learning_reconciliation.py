"""Learning reconciliation (Phase 7, §8–9).

Enforces the invariant: for every eligible terminal AgentAction, both a LearnedOutcome
AND an OutcomeFeedback must exist (unless explicitly excluded). The Phase-6 bridge was
best-effort; this reconciles gaps later — idempotently, tenant-safely, and without ever
modifying the business outcome itself.

Terminal statuses (eligible for learning): approved, executed, auto_executed, rejected,
failed. `pending_approval` / `info_only` are excluded.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("learning_reconciliation")

TERMINAL_STATUSES = ("approved", "executed", "auto_executed", "rejected", "failed")


async def reconcile_action(db: AsyncSession, business_id: UUID | str, action_id: UUID | str) -> dict[str, Any]:
    """Reconcile one terminal action: ensure LearnedOutcome + OutcomeFeedback exist."""
    from app.services.outcome_learning import record_unified_outcome

    result = await record_unified_outcome(db, business_id, action_id, commit=False)
    if result.get("ok"):
        # record_unified_outcome is idempotent for LearnedOutcome (unique constraint) and
        # the OutcomeFeedback bridge now uses ON CONFLICT DO NOTHING.
        return {"action_id": str(action_id), "repaired": bool(result.get("updated")), "status": "ok"}
    return {"action_id": str(action_id), "repaired": False, "status": "failed", "reason": result.get("reason")}


async def reconcile_all(
    db: AsyncSession,
    business_id: UUID | str,
    *,
    limit: int = 200,
    commit: bool = True,
) -> dict[str, Any]:
    """Find terminal actions with a missing LearnedOutcome or OutcomeFeedback and repair.

    Returns metrics: outcomes_checked, missing_feedback, repaired, failed.
    """
    # Terminal actions whose learned outcome is missing (left join).
    res = await db.execute(text("""
        SELECT a.id, a.business_id
        FROM agent_actions a
        LEFT JOIN learned_outcomes lo ON lo.agent_action_id = a.id
        WHERE a.business_id = :b
          AND a.status IN ('approved','executed','auto_executed','rejected','failed')
          AND lo.id IS NULL
        ORDER BY a.created_at DESC
        LIMIT :lim
    """), {"b": str(business_id), "lim": limit})
    missing_lo = [dict(r._mapping) for r in res.fetchall()]

    # Terminal actions whose OutcomeFeedback is missing (left join on the new FK).
    res2 = await db.execute(text("""
        SELECT a.id, a.business_id
        FROM agent_actions a
        LEFT JOIN outcome_feedback of ON of.agent_action_id = a.id
        WHERE a.business_id = :b
          AND a.status IN ('approved','executed','auto_executed','rejected','failed')
          AND of.id IS NULL
        ORDER BY a.created_at DESC
        LIMIT :lim
    """), {"b": str(business_id), "lim": limit})
    missing_of = {str(r.id) for r in res2.fetchall()}

    # Union of actions needing repair.
    to_repair = {r["id"] for r in missing_lo} | missing_of

    repaired = 0
    failed = 0
    for action_id in to_repair:
        try:
            r = await reconcile_action(db, business_id, action_id)
            if r["status"] == "ok":
                repaired += 1
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            logger.warning("reconciliation failed for action %s: %s", action_id, exc)

    if commit:
        await db.commit()

    return {
        "outcomes_checked": len(to_repair),
        "missing_feedback": len(missing_of),
        "missing_learned": len(missing_lo),
        "repaired": repaired,
        "failed": failed,
    }


async def reconcile_all_businesses(db: AsyncSession, limit_per_business: int = 200) -> dict[str, Any]:
    """Reconcile across all active businesses (used by the Celery job)."""
    res = await db.execute(text("SELECT id FROM businesses WHERE is_active = true ORDER BY created_at"))
    business_ids = [str(r[0]) for r in res.fetchall()]

    total_repaired = 0
    total_failed = 0
    total_checked = 0
    for bid in business_ids:
        try:
            r = await reconcile_all(db, bid, limit=limit_per_business, commit=False)
            total_repaired += r["repaired"]
            total_failed += r["failed"]
            total_checked += r["outcomes_checked"]
        except Exception as exc:
            logger.warning("reconciliation failed for business %s: %s", bid, exc)
    await db.commit()
    return {
        "businesses": len(business_ids),
        "outcomes_checked": total_checked,
        "repaired": total_repaired,
        "failed": total_failed,
    }
