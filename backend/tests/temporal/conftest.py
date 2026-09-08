"""Shared fixtures for the Temporal integration suites (tests/temporal/*).

One Real server + one in-process Worker serve the whole directory, so the
retry-probe, sqlite end-to-end, and Postgres integration files all speak to the
SAME durable substrate the production worker runs.

Server selection:
- External: if ``TEMPORAL_ADDRESS`` env is set, connect to that server
  (CI uses the ``temporalio/temporal`` dev-server service at localhost:7233).
- Local: otherwise start ``WorkflowEnvironment.start_local()`` (Temporal CLI
  dev-server binary, no Docker required) and drive the runner against it by
  patching ``Client.connect`` to return the same real client.

The whole directory is Temporal-only: ``USE_TEMPORAL`` is forced true here.
The schema is created once (checked) on the app engine; every test is followed
by a full truncate so each scenario starts from a clean table state.
"""
from __future__ import annotations

import asyncio
import os
from unittest import mock

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USE_TEMPORAL", "true")


from app.config import get_settings  # noqa: E402
from app.database.connection import AsyncSessionLocal, engine  # noqa: E402
from app.database.models import Base  # noqa: E402
from app.orchestration.temporal.worker import build_worker  # noqa: E402
from tests.temporal.probes import PROBE_ACTIVITY_FUNCTIONS, PROBE_WORKFLOWS  # noqa: E402

engine.echo = False  # keep the temporal suite output readable


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def temporal_server():
    external = os.environ.get("TEMPORAL_ADDRESS")
    if external:
        from temporalio.client import Client

        client = await Client.connect(
            external,
            namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
        )
        yield client
        return
    from temporalio.testing import WorkflowEnvironment

    env = await WorkflowEnvironment.start_local()
    try:
        yield env.client
    finally:
        await env.shutdown()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def temporal_worker(temporal_server):
    settings = get_settings()
    worker = build_worker(
        temporal_server,
        settings.TEMPORAL_TASK_QUEUE,
        extra_activities=PROBE_ACTIVITY_FUNCTIONS,
        extra_workflows=PROBE_WORKFLOWS,
    )
    task = asyncio.create_task(worker.run())
    for _ in range(100):
        if task.done():
            break
        if worker.is_running:
            break
        await asyncio.sleep(0.05)
    if task.done():
        exc = task.exception()
        raise RuntimeError(f"temporal worker failed to start: {exc!r}") from exc
    if not worker.is_running:
        raise RuntimeError("temporal worker did not start polling in time")
    try:
        yield worker
    finally:
        await worker.shutdown()
        await task


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def schema_ready():
    """Create the application schema once on the app engine (factory checkfirst)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def point_runner_at_server(temporal_server, temporal_worker, schema_ready):
    """Route ``app.orchestration.runner`` at the real server for this directory.

    The runner is the safe outcome of the Test directive: it connects via a
    genuine ``Client`` (stubbed address discovery only when we started the dev
    server ourselves). All scheduling still happens on the real server we run
    the production worker against.
    """
    from temporalio.client import Client

    external = os.environ.get("TEMPORAL_ADDRESS")
    if external:
        yield
    else:
        with mock.patch.object(Client, "connect", new=mock.AsyncMock(return_value=temporal_server)):
            yield


@pytest_asyncio.fixture(loop_scope="session")
async def db() -> AsyncSession:
    """App-engine session for seeding + assertions (same DB the activities use)."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _truncate_all_tables(schema_ready):
    """Clean table state after each test (worker idle between tests)."""
    yield
    async with AsyncSessionLocal() as session:
        if session.bind.dialect.name == "postgresql":
            names = ", ".join(f'"{t}"' for t in Base.metadata.tables)
            if names:
                await session.execute(text(f"TRUNCATE TABLE {names} CASCADE"))
        else:
            for name in Base.metadata.tables:
                await session.execute(text(f'DELETE FROM "{name}"'))
        await session.commit()