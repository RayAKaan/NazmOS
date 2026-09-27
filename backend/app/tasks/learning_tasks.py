"""Scheduled learning-engine maintenance (Phase 6).

The async helpers are the canonical NazmOS bodies; the ``run_*`` supervisor
wrappers are invoked by Temporal activities (see
``app.orchestration.temporal.activities``).
"""
from __future__ import annotations

from app.database.connection import AsyncSessionLocal, get_sync_session, sync_rls_tenant_context
from app.services.learning_engine import (
    record_feedback,
    refresh_learning,
)
from app.utils.logger import setup_logger

logger = setup_logger("learning_tasks")


async def _record_execution_feedback(execution_job_id: str, business_id: str | None = None) -> dict:
    with sync_rls_tenant_context(str(business_id) if business_id else None):
        async with AsyncSessionLocal() as session:
            from app.database.models import ExecutionJob

            job = await session.get(ExecutionJob, execution_job_id)
            if not job:
                return {"status": "not_found", "execution_job_id": execution_job_id}

            if job.status != "completed":
                return {"status": "skipped", "reason": f"job status is {job.status}"}

            actual_outcome: dict = {}
            if job.result:
                actual_outcome = dict(job.result)
            actual_outcome["status"] = "completed"

            try:
                await record_feedback(
                    session,
                    business_id=job.business_id,
                    execution_job_id=job.id,
                    actual_outcome=actual_outcome,
                    feedback_source="system",
                )
                await session.commit()
                return {"status": "recorded", "execution_job_id": execution_job_id}
            except Exception as exc:
                await session.rollback()
                logger.exception("Failed to record execution feedback", extra={"execution_job_id": execution_job_id})
                raise


async def _refresh_model_performance(business_id: str, window_days: int = 30) -> dict:
    with sync_rls_tenant_context(str(business_id)):
        async with AsyncSessionLocal() as session:
            refreshed = await refresh_learning(session, business_id, window_days=window_days)
            await session.commit()
            return {
                "status": "refreshed",
                "business_id": business_id,
                "window_days": window_days,
                "performance_records": len(refreshed),
            }


def run_refresh_model_performance_all(window_days: int = 30) -> dict:
    """Refresh learning-model performance for every active business.

    Supervisor scope: enumerating active businesses is cross-tenant scheduler
    work; each business refresh runs under its own RLS tenant context inside
    ``_refresh_model_performance``. This corrects the legacy Celery beat call
    that passed ``business_id=None`` to the per-business helper.
    """
    import asyncio

    from sqlalchemy import text

    with get_sync_session() as session:
        ids = [str(r[0]) for r in session.execute(
            text("SELECT id FROM businesses WHERE is_active = true ORDER BY created_at")
        ).fetchall()]

    refreshed = 0
    for business_id in ids:
        try:
            r = asyncio.run(_refresh_model_performance(business_id, window_days=window_days))
            if r.get("status") == "refreshed":
                refreshed += 1
        except Exception as exc:
            logger.warning("model performance refresh failed for %s: %s", business_id, exc)

    return {"status": "completed", "businesses": len(ids), "refreshed": refreshed}
