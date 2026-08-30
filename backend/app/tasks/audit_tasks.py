"""Scheduled continuous auditing (Phase 3, §2).

Runs the reusable Audit Engine on a schedule via Celery Beat (the repo's intended
production scheduler). The daily full audit iterates active businesses; a per-business
variant exists for targeted re-runs.

Idempotency/tenant-safety: the audit engine creates a fresh AuditRun per domain and
persists findings; the debounce in the event processor prevents duplicate event-triggered
runs. Scheduled runs use trigger="scheduled".
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.config import get_settings
from app.database.connection import get_sync_session
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger("celery.audits")

ALL_DOMAINS = ["money_audit", "inventory", "recovery_match", "compliance"]


def run_audits_for_business(business_id: str, domains: list[str] | None = None) -> dict:
    """Run one or more audit domains for a business (sync wrapper over the async engine)."""
    from app.services.audit_engine import run_audit
    from app.database.connection import AsyncSessionLocal

    async def _run() -> dict:
        results = []
        async with AsyncSessionLocal() as session:
            for domain in (domains or ALL_DOMAINS):
                try:
                    r = await run_audit(session, business_id, domain, trigger="scheduled", commit=False)
                    results.append(r)
                except Exception as exc:
                    logger.warning("scheduled audit %s for %s failed: %s", domain, business_id, exc)
                    results.append({"domain": domain, "status": "failed", "error": str(exc)[:500]})
            await session.commit()
        return {"business_id": business_id, "audits": results}

    return asyncio.run(_run())


def run_goal_progress_snapshot() -> dict:
    """Snapshot goal progress for all active businesses (Phase 5 §9, daily)."""
    import asyncio
    from app.database.connection import AsyncSessionLocal
    from app.services.goal_service import snapshot_goal_progress

    async def _run() -> dict:
        with get_sync_session() as session:
            ids = [str(r[0]) for r in session.execute(
                text("SELECT id FROM businesses WHERE is_active = true ORDER BY created_at")
            ).fetchall()]
        total = 0
        async with AsyncSessionLocal() as session:
            for business_id in ids:
                try:
                    r = await snapshot_goal_progress(session, business_id, source="scheduled", commit=False)
                    total += r.get("snapshots", 0)
                except Exception as exc:
                    logger.warning("goal snapshot failed for %s: %s", business_id, exc)
            await session.commit()
        return {"status": "completed", "snapshots": total, "businesses": len(ids)}

    return asyncio.run(_run())


def run_learning_reconciliation() -> dict:
    """Reconcile LearnedOutcome ↔ OutcomeFeedback consistency (Phase 7 §9)."""
    import asyncio
    from app.database.connection import AsyncSessionLocal
    from app.services.learning_reconciliation import reconcile_all_businesses

    async def _run() -> dict:
        async with AsyncSessionLocal() as session:
            return await reconcile_all_businesses(session)

    return asyncio.run(_run())


def run_daily_full_audit() -> dict:
    """Daily scheduled full audit across all active businesses (idempotent, tenant-safe)."""
    with get_sync_session() as session:
        result = session.execute(
            text("SELECT id FROM businesses WHERE is_active = true ORDER BY created_at")
        )
        business_ids = [str(r[0]) for r in result.fetchall()]

    audited = 0
    for business_id in business_ids:
        try:
            outcome = run_audits_for_business(business_id)
            audited += 1
        except Exception as exc:
            logger.error("daily audit failed for business %s: %s", business_id, exc)

    return {"status": "completed", "businesses_audited": audited, "total_businesses": len(business_ids)}


if settings.USE_CELERY:
    from app.celery_app import celery_app

    @celery_app.task(bind=True, name="app.tasks.audit_tasks.daily_full_audit")
    def daily_full_audit(self):
        return run_daily_full_audit()

    @celery_app.task(name="app.tasks.audit_tasks.audit_business")
    def audit_business(business_id: str, domains: list[str] | None = None):
        return run_audits_for_business(business_id, domains)

    @celery_app.task(name="app.tasks.audit_tasks.goal_progress_snapshot")
    def goal_progress_snapshot():
        return run_goal_progress_snapshot()

    @celery_app.task(name="app.tasks.audit_tasks.learning_reconciliation")
    def learning_reconciliation():
        return run_learning_reconciliation()
