"""Prove REAL Temporal server-side retry wiring with production-shaped policies.

No database involved: these drive the test-only retry probe workflows through
the real server we run the production worker against and assert the actual
attempt counts Temporal applied — proving that:
  - the transient classification genuinely retries (attempts == 2), and
  - the deterministic classification genuinely does NOT retry (fails fast).
"""
from __future__ import annotations

import uuid

import pytest
from pytest import mark


@mark.asyncio(loop_scope="session")
async def test_transient_probe_is_actually_retried_once(temporal_server):
    res = await temporal_server.execute_workflow(
        "retry_probe_transient",
        {"fail_through_attempt": 1},
        id=f"probe-transient-{uuid.uuid4()}",
        task_queue="nazm-execution",
    )
    assert res == {"ok": True, "attempts": 2}, "transient policy must retry exactly once"


@mark.asyncio(loop_scope="session")
async def test_deterministic_probe_is_never_retried(temporal_server):
    res = await temporal_server.execute_workflow(
        "retry_probe_no_retry",
        {"fail_through_attempt": 1},
        id=f"probe-no-retry-{uuid.uuid4()}",
        task_queue="nazm-execution",
    )
    assert res["ok"] is False, "no-retry policy must fail fast without a second attempt"
    assert "attempt" in res["error"]


@mark.asyncio(loop_scope="session")
async def test_probe_workflows_live_on_the_shared_worker(temporal_worker, temporal_server):
    """The probes are registered server-side by the very worker hosting real workflows."""
    assert temporal_worker.is_running, "worker hosting probes must be started/healthy"
    # A real (retry-free) activity executes end-to-end through that worker.
    res = await temporal_server.execute_workflow(
        "retry_probe_transient",
        {"fail_through_attempt": 0},
        id=f"probe-health-{uuid.uuid4()}",
        task_queue="nazm-execution",
    )
    assert res == {"ok": True, "attempts": 1}