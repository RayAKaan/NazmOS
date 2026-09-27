"""Compliance / data-retention automation (GDPR / PDPL).

``run_process_pending_deletions`` runs on a schedule and hard-purges any
``deletion_requests`` rows whose ``scheduled_purge_at`` has passed.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.database.connection import sync_rls_tenant_context
from app.database.models import DeletionRequest
from app.routers.compliance import _hard_delete_business_data
from app.utils.logger import setup_logger

logger = setup_logger("compliance_tasks")


async def _purge_business(business_id: UUID) -> None:
    """Purge one business and mark its deletion request completed.

    Scoped to ``business_id`` so every table delete sees only that tenant's
    rows under RLS.
    """
    with sync_rls_tenant_context(str(business_id)):
        async with AsyncSessionLocal() as session:
            await _hard_delete_business_data(session, business_id)

            result = await session.execute(
                select(DeletionRequest).where(
                    DeletionRequest.business_id == business_id,
                    DeletionRequest.status == "pending",
                )
            )
            request = result.scalar_one_or_none()
            if request:
                request.status = "completed"
                request.purged_at = datetime.now(timezone.utc)
                await session.commit()

            logger.info(
                "Business data purged by scheduled deletion task",
                extra={"business_id": str(business_id)},
            )


def run_process_pending_deletions() -> dict:
    """Synchronous entry point used by the Temporal ``process_pending_deletions`` activity.

    Supervisor scope: enumerating pending deletion requests is cross-tenant
    scheduler work; each business purge then runs RLS-scoped in ``_purge_business``.
    """

    async def _process() -> dict:
        purged = 0
        skipped = 0
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(DeletionRequest).where(
                    DeletionRequest.status == "pending",
                    DeletionRequest.scheduled_purge_at <= now,
                )
            )
            requests = result.scalars().all()

        for request in requests:
            try:
                await _purge_business(request.business_id)
                purged += 1
            except Exception as exc:
                logger.exception(
                    "Failed to purge business during scheduled deletion",
                    extra={"business_id": str(request.business_id), "error": str(exc)},
                )
                skipped += 1

        return {"purged": purged, "skipped": skipped}

    return asyncio.run(_process())
