"""Temporal Schedule registration for formerly-Celery-Beat operations.

Every operation that was defined in ``app/celery_app.py``'s ``beat_schedule``
is expressed here as a Temporal Schedule running on the same
``TEMPORAL_TASK_QUEUE`` as the rest of the NazmOS execution activities.

``ensure_default_schedules`` is idempotent and is called once at worker start
(``app.orchestration.temporal.worker._main``) and/or via the one-shot CLI:

    python -m app.orchestration.temporal.schedules

Production topology (docker-compose) will call the worker entry point; the
CLI exists for one-off manual seeding during migration.
"""
from __future__ import annotations

import datetime
from typing import Any

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
)


# ── Default schedule definitions ───────────────────────────────────────
# (wf_name, ScheduleSpec, default_payload)

DEFAULT_SCHEDULES: list[tuple[str, ScheduleSpec, dict]] = [
    # ── Every minute (former beat: process-unprocessed-events, 60s) ──
    (
        "drain_unprocessed_events",
        ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=datetime.timedelta(seconds=60))],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "drain_unprocessed_events"},
    ),
    # ── POS sweep every 5 minutes (NEW schedule, was dormant outside beat) ──
    (
        "pos_sweep",
        ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=datetime.timedelta(seconds=300))],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "pos_sweep"},
    ),
    # ── Learning reconciliation every hour (former beat: learning-reconciliation) ──
    (
        "learning_reconciliation",
        ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=datetime.timedelta(seconds=3600))],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "learning_reconciliation"},
    ),
    # ── Daily cron jobs (former beat_schedule lines 84+) ──
    (
        "rebuild_daily_summaries",
        ScheduleSpec(
            cron_expressions=["0 1 * * *"],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "rebuild_daily_summaries"},
    ),
    (
        "cleanup_stale_uploads",
        ScheduleSpec(
            cron_expressions=["0 2 * * *"],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "cleanup_stale_uploads"},
    ),
    (
        "forecast_refresh_all",
        ScheduleSpec(
            cron_expressions=["0 3 * * *"],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "forecast_refresh_all"},
    ),
    (
        "process_pending_deletions",
        ScheduleSpec(
            cron_expressions=["0 4 * * *"],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "process_pending_deletions"},
    ),
    (
        "refresh_model_performance",
        ScheduleSpec(
            cron_expressions=["0 5 * * *"],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "refresh_model_performance"},
    ),
    (
        "daily_full_audit",
        ScheduleSpec(
            cron_expressions=["0 6 * * *"],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "daily_full_audit"},
    ),
    (
        "goal_progress_snapshot",
        ScheduleSpec(
            cron_expressions=["0 7 * * *"],
            time_zone_name="Asia/Riyadh",
        ),
        {"operation": "goal_progress_snapshot"},
    ),
]


async def ensure_default_schedules(client: Client, task_queue: str) -> None:
    """Idempotently create every default NazmOS schedule.

    Existing schedules with the same ``nazm-<wf>`` id are left untouched.
    """
    existing = {s.id async for s in await client.list_schedules()}
    for wf_name, spec, payload in DEFAULT_SCHEDULES:
        schedule_id = f"nazm-{wf_name}"
        if schedule_id in existing:
            continue
        try:
            await client.create_schedule(
                schedule_id,
                Schedule(
                    action=ScheduleActionStartWorkflow(
                        wf_name,
                        args=[payload],
                        id=f"nazm-{wf_name}-run",
                        task_queue=task_queue,
                    ),
                    spec=spec,
                    policy=SchedulePolicy(
                        overlap=ScheduleOverlapPolicy.ALLOW_ALL,
                    ),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - schedule creation is best-effort
            import logging

            logging.getLogger("temporal.schedules").warning(
                "Could not create schedule %s: %s", schedule_id, exc
            )


# ── CLI entry point ────────────────────────────────────────────────────

async def _seed_cli() -> None:
    import asyncio

    from app.config import get_settings

    settings = get_settings()
    client = await asyncio.wait_for(
        Client.connect(
            settings.TEMPORAL_ADDRESS,
            namespace=settings.TEMPORAL_NAMESPACE,
        ),
        timeout=settings.TEMPORAL_CONNECT_TIMEOUT_SECONDS,
    )
    await ensure_default_schedules(client, settings.TEMPORAL_TASK_QUEUE)


if __name__ == "__main__":
    import asyncio

    asyncio.run(_seed_cli())