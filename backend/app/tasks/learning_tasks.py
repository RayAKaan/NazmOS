"""Celery tasks for the Learning Engine (Phase 6).
"""
from __future__ import annotations

from app.config import get_settings
from app.database.connection import AsyncSessionLocal
from app.services.learning_engine import (
    record_feedback,
    refresh_learning,
)
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger("celery.learning")


async def _record_execution_feedback(execution_job_id: str) -> dict:
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
    async with AsyncSessionLocal() as session:
        refreshed = await refresh_learning(session, business_id, window_days=window_days)
        await session.commit()
        return {
            "status": "refreshed",
            "business_id": business_id,
            "window_days": window_days,
            "performance_records": len(refreshed),
        }


if settings.USE_CELERY:
    from app.celery_app import celery_app

    @celery_app.task(name="app.tasks.learning_tasks.record_execution_feedback")
    def record_execution_feedback_task(execution_job_id: str) -> dict:
        import asyncio
        return asyncio.run(_record_execution_feedback(execution_job_id))

    @celery_app.task(name="app.tasks.learning_tasks.refresh_model_performance")
    def refresh_model_performance_task(business_id: str, window_days: int = 30) -> dict:
        import asyncio
        return asyncio.run(_refresh_model_performance(business_id, window_days))
