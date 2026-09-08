"""Temporal worker hosting the NazmOS execution workflows + activities.

Entry point for the ``nazmos-worker`` service: ``python -m app.orchestration.temporal.worker``.
In-process test workers call ``build_worker``.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, Awaitable, Callable

from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from app.config import get_settings
from app.orchestration.temporal.activities import ALL_ACTIVITY_FUNCTIONS
from app.orchestration.temporal.workflows import WORKFLOWS


def build_worker(
    client: Client,
    task_queue: str | None = None,
    *,
    extra_activities: Sequence[Callable[[dict], Awaitable[Any]]] = (),
    extra_workflows: Sequence[type] = (),
) -> Worker:
    """Build an unsandboxed Worker hosting every NazmOS activity and workflow.

    ``extra_activities`` / ``extra_workflows`` are for test-only additions
    (e.g. retry probes); the production service registers none.
    """
    return Worker(
        client,
        task_queue=task_queue or get_settings().TEMPORAL_TASK_QUEUE,
        workflows=[*WORKFLOWS.values(), *extra_workflows],
        activities=[*ALL_ACTIVITY_FUNCTIONS, *extra_activities],
        # The SDK asyncio sandbox would reject our SQLAlchemy-backed activities
        # and non-whitelisted workflow imports (e.g. structlog's rich tracebacks).
        # Determinism is enforced structurally (workflows only call
        # execute_activity), not via sandbox, so run workflows unsandboxed.
        workflow_runner=UnsandboxedWorkflowRunner(),
    )


async def _main() -> None:
    settings = get_settings()
    client = await Client.connect(
        settings.TEMPORAL_ADDRESS,
        namespace=settings.TEMPORAL_NAMESPACE,
    )
    worker = build_worker(client, settings.TEMPORAL_TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())